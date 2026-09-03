package de.lamskemper.karaoke.song;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SongRepository extends JpaRepository<Song, Long> {

    java.util.List<Song> findAllByOrderByCreatedAtDesc();
}
