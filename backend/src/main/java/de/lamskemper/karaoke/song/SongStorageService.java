package de.lamskemper.karaoke.song;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Legt die von der Konvertierung gelieferten Artefakte pro Song in einem
 * eigenen Unterordner unter karaoke.storage.base-dir ab. Zwei Layouts:
 *   Einstimmig (bisher):  {base-dir}/{songId}/instrumental.wav, /lyrics.json
 *   Mehrstimmig (Slice 5): {base-dir}/{songId}/tracks/{voiceName}/audio.<ext>, /lyrics.json
 */
@Service
public class SongStorageService {

    private final Path baseDir;

    public SongStorageService(@Value("${karaoke.storage.base-dir}") String baseDir) {
        this.baseDir = Path.of(baseDir).toAbsolutePath().normalize();
        try {
            Files.createDirectories(this.baseDir);
        } catch (IOException e) {
            throw new UncheckedIOException("Konnte Storage-Basisordner nicht anlegen: " + this.baseDir, e);
        }
    }

    public String store(Long songId, String fileName, MultipartFile file) {
        try {
            Path songDir = baseDir.resolve(String.valueOf(songId));
            Files.createDirectories(songDir);
            Path target = songDir.resolve(fileName);
            file.transferTo(target);
            return baseDir.relativize(target).toString().replace('\\', '/');
        } catch (IOException e) {
            throw new UncheckedIOException("Konnte Datei nicht speichern: " + fileName, e);
        }
    }

    public String storeTrack(Long songId, String voiceName, String fileName, MultipartFile file) {
        try {
            Path trackDir = baseDir.resolve(String.valueOf(songId)).resolve("tracks").resolve(voiceName);
            Files.createDirectories(trackDir);
            Path target = trackDir.resolve(fileName);
            file.transferTo(target);
            return baseDir.relativize(target).toString().replace('\\', '/');
        } catch (IOException e) {
            throw new UncheckedIOException("Konnte Track-Datei nicht speichern: " + voiceName + "/" + fileName, e);
        }
    }

    public Path resolve(String relativePath) {
        return baseDir.resolve(relativePath).normalize();
    }
}
