package de.lamskemper.karaoke.score;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ScoreRepository extends JpaRepository<ScoreEntry, Long> {

    // Bestenliste eines Songs: beste Trefferquote zuerst, bei Gleichstand das juengste Ergebnis
    List<ScoreEntry> findBySongIdOrderByPercentageDescCreatedAtDesc(Long songId);
}
