package de.lamskemper.karaoke.song;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * Ein registrierter Song. Die eigentliche Konvertierung (Vocal-Separation,
 * Pitch-Kurve, Lyrics-Timing) passiert AUSSERHALB der App (siehe
 * C:\ki\karaoke-app\konverter\convert.py). Die App speichert hier nur die
 * fertigen Artefakte und Metadaten.
 *
 * Zwei Formen:
 * - Einstimmig (bisher): instrumentalPath + lyricsPath direkt am Song, voiceTracks leer
 * - Mehrstimmig (Vertical Slice 5, Chorlieder): voiceTracks enthaelt je eine Zeile pro
 *   Stimme (z.B. Klavier, Sopran, Alt, Tenor, Bass). instrumentalPath/lyricsPath zeigen
 *   dann auf die erste singbare Stimme, rein zur Abwaertskompatibilitaet der alten
 *   /instrumental und /lyrics Endpunkte (aeltere Frontend-Views sehen so wenigstens
 *   eine spielbare Stimme statt gar nichts).
 */
@Entity
public class Song {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    // Relativer Pfad unter karaoke.storage.base-dir, z.B. "3/instrumental.wav"
    @Column(nullable = false)
    private String instrumentalPath;

    // Relativer Pfad unter karaoke.storage.base-dir, z.B. "3/lyrics.json"
    @Column(nullable = false)
    private String lyricsPath;

    // EAGER, weil open-in-view=false ist und jede Song-Response die Stimmen
    // mitrendert (SongResponse.from). Bei 2 Nutzern / wenigen Songs ist das
    // entstehende N+1 auf findAll voellig unkritisch.
    @OneToMany(mappedBy = "song", fetch = FetchType.EAGER)
    @OrderBy("sortOrder ASC")
    private List<VoiceTrack> voiceTracks = new ArrayList<>();

    protected Song() {
        // fuer JPA
    }

    public Song(String title, String instrumentalPath, String lyricsPath) {
        this.title = title;
        this.instrumentalPath = instrumentalPath;
        this.lyricsPath = lyricsPath;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getInstrumentalPath() {
        return instrumentalPath;
    }

    public String getLyricsPath() {
        return lyricsPath;
    }

    public List<VoiceTrack> getVoiceTracks() {
        return voiceTracks;
    }

    void updatePaths(String instrumentalPath, String lyricsPath) {
        this.instrumentalPath = instrumentalPath;
        this.lyricsPath = lyricsPath;
    }

    void addVoiceTrackInMemory(VoiceTrack track) {
        voiceTracks.add(track);
    }
}
