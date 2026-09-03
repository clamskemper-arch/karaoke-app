package de.lamskemper.karaoke.song;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

/**
 * Eine einzelne Stimme/Spur innerhalb eines mehrstimmigen Songs (Vertical Slice 5,
 * Chorlieder mit Klavier + Sopran/Alt/Tenor/Bass). Quelle der Audiodateien: Export
 * aus einer Notensatz-Software (z.B. MuseScore), nicht automatische Stimmtrennung -
 * siehe Align-Notiz in der Projekt-Doku vom 01.09.2026.
 *
 * lyricsPath ist absichtlich nullable: reine Begleit-Stimmen wie Klavier haben keinen
 * Text/keine Ton-Referenz zum Mitsingen, sollen aber trotzdem als zuschaltbare Stimme
 * im Mixer auftauchen.
 */
@Entity
public class VoiceTrack {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(optional = false)
    @JoinColumn(name = "song_id", nullable = false)
    private Song song;

    // Frei vergebener Stimmname, z.B. "Klavier", "Sopran", "Alt", "Tenor", "Bass".
    // Wird auch als Ordnername unter der Song-Storage verwendet, siehe SongStorageService -
    // deshalb im Controller auf [A-Za-z0-9_-]+ validiert.
    @Column(nullable = false)
    private String voiceName;

    // Relativer Pfad unter karaoke.storage.base-dir, z.B. "12/tracks/Tenor/audio.wav"
    @Column(nullable = false)
    private String audioPath;

    // Relativer Pfad unter karaoke.storage.base-dir, z.B. "12/tracks/Tenor/lyrics.json".
    // null = keine Lyrics/Pitch-Referenz vorhanden (z.B. bei reiner Klavierbegleitung).
    private String lyricsPath;

    // Anzeige-/Ladereihenfolge im Mixer, damit z.B. immer Klavier zuerst kommt.
    @Column(nullable = false)
    private int sortOrder;

    protected VoiceTrack() {
        // fuer JPA
    }

    public VoiceTrack(Song song, String voiceName, String audioPath, String lyricsPath, int sortOrder) {
        this.song = song;
        this.voiceName = voiceName;
        this.audioPath = audioPath;
        this.lyricsPath = lyricsPath;
        this.sortOrder = sortOrder;
    }

    public Long getId() {
        return id;
    }

    public Song getSong() {
        return song;
    }

    public String getVoiceName() {
        return voiceName;
    }

    public String getAudioPath() {
        return audioPath;
    }

    public String getLyricsPath() {
        return lyricsPath;
    }

    public boolean hasLyrics() {
        return lyricsPath != null;
    }

    public int getSortOrder() {
        return sortOrder;
    }
}
