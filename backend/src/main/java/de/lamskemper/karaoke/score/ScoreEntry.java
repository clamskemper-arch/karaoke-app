package de.lamskemper.karaoke.score;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

import java.time.Instant;

/**
 * Ein gespeichertes Sing-Ergebnis (Vertical Slice 3.5). Bewusst schlank:
 * kein echtes Login, nur ein frei eingegebener Name pro Durchgang - der
 * Zugriff ist ueber Tailscale schon auf Christian + Eli begrenzt.
 *
 * songId statt einer @ManyToOne-Beziehung, und songTitle als Schnappschuss:
 * so bleibt die Bestenliste lesbar, auch wenn ein Song spaeter geloescht
 * wird, und es gibt keine Lazy-Loading-Fallstricke wie bei Song.voiceTracks.
 */
@Entity
public class ScoreEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long songId;

    @Column(nullable = false)
    private String songTitle;

    @Column(nullable = false)
    private String playerName;

    // Bei Chorliedern die selbst gesungene Stimme, sonst null
    private String voiceName;

    @Column(nullable = false)
    private int percentage;

    @Column(nullable = false)
    private int bestCombo;

    @Column(nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected ScoreEntry() {
        // fuer JPA
    }

    public ScoreEntry(Long songId, String songTitle, String playerName, String voiceName,
                      int percentage, int bestCombo) {
        this.songId = songId;
        this.songTitle = songTitle;
        this.playerName = playerName;
        this.voiceName = voiceName;
        this.percentage = percentage;
        this.bestCombo = bestCombo;
    }

    public Long getId() {
        return id;
    }

    public Long getSongId() {
        return songId;
    }

    public String getSongTitle() {
        return songTitle;
    }

    public String getPlayerName() {
        return playerName;
    }

    public String getVoiceName() {
        return voiceName;
    }

    public int getPercentage() {
        return percentage;
    }

    public int getBestCombo() {
        return bestCombo;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
