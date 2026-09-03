package de.lamskemper.karaoke.song;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface VoiceTrackRepository extends JpaRepository<VoiceTrack, Long> {

    Optional<VoiceTrack> findBySong_IdAndVoiceName(Long songId, String voiceName);
}
