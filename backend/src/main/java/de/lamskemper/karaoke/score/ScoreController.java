package de.lamskemper.karaoke.score;

import de.lamskemper.karaoke.song.SongRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.util.List;

/**
 * Sing-Ergebnisse speichern und je Song als Bestenliste ausliefern
 * (Vertical Slice 3.5). Das Frontend zeigt am Songende ein Namensfeld;
 * ohne Namen wird nichts gespeichert - dann kommt hier gar kein POST an.
 */
@RestController
@RequestMapping("/api/scores")
public class ScoreController {

    private final ScoreRepository scoreRepository;
    private final SongRepository songRepository;

    public ScoreController(ScoreRepository scoreRepository, SongRepository songRepository) {
        this.scoreRepository = scoreRepository;
        this.songRepository = songRepository;
    }

    @GetMapping
    public List<ScoreView> list(@RequestParam Long songId) {
        return scoreRepository.findBySongIdOrderByPercentageDescCreatedAtDesc(songId)
                .stream()
                .map(ScoreView::from)
                .toList();
    }

    @PostMapping
    public ScoreView save(@Valid @RequestBody NewScore body) {
        String song = songRepository.findById(body.songId())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Song nicht gefunden"))
                .getTitle();

        String name = body.playerName().trim();
        String voice = body.voiceName() == null || body.voiceName().isBlank() ? null : body.voiceName().trim();

        ScoreEntry saved = scoreRepository.save(new ScoreEntry(
                body.songId(),
                song,
                name,
                voice,
                clampPercent(body.percentage()),
                Math.max(0, body.bestCombo())
        ));
        return ScoreView.from(saved);
    }

    private static int clampPercent(int value) {
        return Math.max(0, Math.min(100, value));
    }

    public record NewScore(
            @NotNull Long songId,
            @NotBlank String playerName,
            String voiceName,
            int percentage,
            int bestCombo
    ) {
    }

    public record ScoreView(
            Long id,
            String playerName,
            String voiceName,
            int percentage,
            int bestCombo,
            Instant createdAt
    ) {
        static ScoreView from(ScoreEntry e) {
            return new ScoreView(e.getId(), e.getPlayerName(), e.getVoiceName(),
                    e.getPercentage(), e.getBestCombo(), e.getCreatedAt());
        }
    }
}
