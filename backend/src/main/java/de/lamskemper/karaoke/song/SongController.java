package de.lamskemper.karaoke.song;

import jakarta.validation.constraints.NotBlank;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.MediaTypeFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import org.springframework.web.server.ResponseStatusException;

import java.net.MalformedURLException;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Registrieren und Abspielen von Songs. Die eigentliche Konvertierung
 * (Vocal-Separation, Pitch-Kurve, Lyrics-Timing) findet separat via
 * `C:\ki\karaoke-app\konverter\convert.py` statt - hier kommen nur noch
 * die fertigen Artefakte an.
 *
 * Zwei Registrierungswege:
 * - POST /api/songs: einstimmig (instrumental.wav + lyrics.json), wie bisher - unveraendert
 * - POST /api/songs/multitrack: mehrstimmig (Vertical Slice 5, Chorlieder) - je Stimme ein
 *   Audio-Pflichtfeld "audio_{Stimmname}" und ein optionales Lyrics-Feld "lyrics_{Stimmname}"
 *   (fehlt bei reinen Begleit-Stimmen wie Klavier). Welche Stimmen ueberhaupt erwartet werden,
 *   steht in "voiceNames" (kommagetrennt, z.B. "Klavier,Sopran,Alt,Tenor,Bass").
 */
@RestController
@RequestMapping("/api/songs")
public class SongController {

    private final SongRepository songRepository;
    private final VoiceTrackRepository voiceTrackRepository;
    private final SongStorageService storageService;

    public SongController(SongRepository songRepository, VoiceTrackRepository voiceTrackRepository,
                           SongStorageService storageService) {
        this.songRepository = songRepository;
        this.voiceTrackRepository = voiceTrackRepository;
        this.storageService = storageService;
    }

    @GetMapping
    public List<SongResponse> list() {
        return songRepository.findAllByOrderByCreatedAtDesc()
                .stream()
                .map(SongResponse::from)
                .toList();
    }

    @GetMapping("/{id}")
    public SongResponse get(@PathVariable Long id) {
        return SongResponse.from(findSongOrThrow(id));
    }

    @PostMapping
    public ResponseEntity<SongResponse> register(
            @RequestParam @NotBlank String title,
            @RequestParam("instrumental") MultipartFile instrumental,
            @RequestParam("lyrics") MultipartFile lyrics
    ) {
        if (instrumental.isEmpty()) {
            throw badRequest("instrumental.wav fehlt");
        }
        if (lyrics.isEmpty()) {
            throw badRequest("lyrics.json fehlt");
        }

        // 1. Song ohne Pfade anlegen, um eine ID zu bekommen (Ordnername)
        Song song = songRepository.save(new Song(title, "", ""));

        // 2. Artefakte in {base-dir}/{id}/ ablegen
        String instrumentalPath = storageService.store(song.getId(), "instrumental.wav", instrumental);
        String lyricsPath = storageService.store(song.getId(), "lyrics.json", lyrics);

        // 3. Song mit den tatsaechlichen Pfaden aktualisieren
        song.updatePaths(instrumentalPath, lyricsPath);
        songRepository.save(song);

        return ResponseEntity.ok(SongResponse.from(song));
    }

    @PostMapping("/multitrack")
    public ResponseEntity<SongResponse> registerMultitrack(
            @RequestParam @NotBlank String title,
            @RequestParam String voiceNames,
            MultipartHttpServletRequest request
    ) {
        List<String> names = Arrays.stream(voiceNames.split(","))
                .map(String::trim)
                .filter(name -> !name.isEmpty())
                .toList();
        if (names.isEmpty()) {
            throw badRequest("voiceNames darf nicht leer sein (kommagetrennte Liste, z.B. 'Klavier,Sopran,Alt,Tenor,Bass')");
        }
        for (String name : names) {
            if (!name.matches("[A-Za-z0-9_-]+")) {
                throw badRequest("Ungueltiger Stimmname '" + name + "' (nur Buchstaben, Zahlen, - und _ erlaubt)");
            }
        }

        Map<String, MultipartFile> files = request.getFileMap();
        boolean anyLyrics = false;
        for (String name : names) {
            MultipartFile audio = files.get("audio_" + name);
            if (audio == null || audio.isEmpty()) {
                throw badRequest("Audio fuer Stimme '" + name + "' fehlt (Formularfeld audio_" + name + ")");
            }
            MultipartFile lyrics = files.get("lyrics_" + name);
            if (lyrics != null && !lyrics.isEmpty()) {
                anyLyrics = true;
            }
        }
        if (!anyLyrics) {
            throw badRequest("Mindestens eine Stimme braucht lyrics.json - sonst gibt's nichts zum Mitsingen");
        }

        Song song = songRepository.save(new Song(title, "", ""));

        String primaryAudioPath = null;
        String primaryLyricsPath = null;
        int sortOrder = 0;
        for (String name : names) {
            MultipartFile audio = files.get("audio_" + name);
            MultipartFile lyrics = files.get("lyrics_" + name);

            String audioFileName = "audio." + extensionOf(audio.getOriginalFilename(), "wav");
            String audioPath = storageService.storeTrack(song.getId(), name, audioFileName, audio);

            String lyricsPath = null;
            if (lyrics != null && !lyrics.isEmpty()) {
                lyricsPath = storageService.storeTrack(song.getId(), name, "lyrics.json", lyrics);
            }

            VoiceTrack track = new VoiceTrack(song, name, audioPath, lyricsPath, sortOrder++);
            voiceTrackRepository.save(track);
            song.addVoiceTrackInMemory(track);

            // Erste singbare Stimme wird "primary" fuer die alten /instrumental + /lyrics
            // Endpunkte, damit auch aeltere Frontend-Views wenigstens eine Stimme sehen.
            if (primaryAudioPath == null && lyricsPath != null) {
                primaryAudioPath = audioPath;
                primaryLyricsPath = lyricsPath;
            }
        }

        song.updatePaths(primaryAudioPath, primaryLyricsPath);
        songRepository.save(song);

        return ResponseEntity.ok(SongResponse.from(song));
    }

    @GetMapping("/{id}/instrumental")
    public ResponseEntity<Resource> instrumental(@PathVariable Long id) {
        return serveFile(id, Song::getInstrumentalPath, MediaType.parseMediaType("audio/wav"));
    }

    @GetMapping("/{id}/lyrics")
    public ResponseEntity<Resource> lyrics(@PathVariable Long id) {
        return serveFile(id, Song::getLyricsPath, MediaType.APPLICATION_JSON);
    }

    @GetMapping("/{id}/tracks/{voiceName}/audio")
    public ResponseEntity<Resource> trackAudio(@PathVariable Long id, @PathVariable String voiceName) {
        return serveTrackFile(id, voiceName, VoiceTrack::getAudioPath, MediaType.parseMediaType("audio/wav"));
    }

    @GetMapping("/{id}/tracks/{voiceName}/lyrics")
    public ResponseEntity<Resource> trackLyrics(@PathVariable Long id, @PathVariable String voiceName) {
        return serveTrackFile(id, voiceName, VoiceTrack::getLyricsPath, MediaType.APPLICATION_JSON);
    }

    private Song findSongOrThrow(Long id) {
        return songRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Song nicht gefunden"));
    }

    private ResponseEntity<Resource> serveFile(Long id, Function<Song, String> pathFn, MediaType fallbackMediaType) {
        Song song = findSongOrThrow(id);
        return serveResource(storageService.resolve(pathFn.apply(song)), fallbackMediaType);
    }

    private ResponseEntity<Resource> serveTrackFile(Long songId, String voiceName,
            Function<VoiceTrack, String> pathFn, MediaType fallbackMediaType) {
        VoiceTrack track = voiceTrackRepository.findBySong_IdAndVoiceName(songId, voiceName)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Stimme nicht gefunden: " + voiceName));
        String relativePath = pathFn.apply(track);
        if (relativePath == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "Fuer diese Stimme gibt's das nicht (z.B. keine Lyrics bei reiner Begleitung)");
        }
        return serveResource(storageService.resolve(relativePath), fallbackMediaType);
    }

    private ResponseEntity<Resource> serveResource(Path path, MediaType fallbackMediaType) {
        try {
            Resource resource = new UrlResource(path.toUri());
            if (!resource.exists()) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Datei fehlt: " + path);
            }
            MediaType mediaType = MediaTypeFactory.getMediaType(resource).orElse(fallbackMediaType);
            return ResponseEntity.ok()
                    .contentType(mediaType)
                    .header(HttpHeaders.CACHE_CONTROL, "no-store")
                    .body(resource);
        } catch (MalformedURLException e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Ungueltiger Dateipfad", e);
        }
    }

    private static ResponseStatusException badRequest(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }

    private static String extensionOf(String originalFilename, String fallback) {
        if (originalFilename == null) {
            return fallback;
        }
        int dot = originalFilename.lastIndexOf('.');
        if (dot < 0 || dot == originalFilename.length() - 1) {
            return fallback;
        }
        String ext = originalFilename.substring(dot + 1).toLowerCase();
        return ext.matches("[a-z0-9]+") ? ext : fallback;
    }
}
