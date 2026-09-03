package de.lamskemper.karaoke.song;

import java.time.Instant;
import java.util.List;

/**
 * instrumentalUrl/lyricsUrl bleiben aus Abwaertskompatibilitaet erhalten (zeigen bei
 * mehrstimmigen Songs auf die erste singbare Stimme). "tracks" ist der neue, einheitliche
 * Weg: bei mehrstimmigen Songs eine Zeile pro echter Stimme, bei aelteren einstimmigen
 * Songs ein synthetischer Eintrag "Tenor" (bisher waren alle registrierten Songs
 * Tenor-Aufnahmen von Christian) - so muss das Frontend nicht zwischen alt/neu
 * unterscheiden, sobald es auf "tracks" umgestellt ist.
 */
public record SongResponse(
        Long id,
        String title,
        Instant createdAt,
        String instrumentalUrl,
        String lyricsUrl,
        List<TrackResponse> tracks
) {

    public record TrackResponse(String voiceName, String audioUrl, String lyricsUrl) {
    }

    static SongResponse from(Song song) {
        List<TrackResponse> tracks = song.getVoiceTracks().isEmpty()
                ? legacyTrack(song)
                : song.getVoiceTracks().stream()
                        .map(t -> new TrackResponse(
                                t.getVoiceName(),
                                "/api/songs/%d/tracks/%s/audio".formatted(song.getId(), t.getVoiceName()),
                                t.hasLyrics() ? "/api/songs/%d/tracks/%s/lyrics".formatted(song.getId(), t.getVoiceName()) : null
                        ))
                        .toList();

        return new SongResponse(
                song.getId(),
                song.getTitle(),
                song.getCreatedAt(),
                "/api/songs/%d/instrumental".formatted(song.getId()),
                "/api/songs/%d/lyrics".formatted(song.getId()),
                tracks
        );
    }

    private static List<TrackResponse> legacyTrack(Song song) {
        return List.of(new TrackResponse(
                "Tenor",
                "/api/songs/%d/instrumental".formatted(song.getId()),
                "/api/songs/%d/lyrics".formatted(song.getId())
        ));
    }
}
