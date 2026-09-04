package de.lamskemper.karaoke.share;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * Stellt vorbereitete .ksong-Bundles im Heimnetz zum Download bereit.
 *
 * Gedacht fuer den simplen Offline-Workflow ohne Client-Server-Betrieb: das
 * Handy oeffnet im Browser {@code http://<pc-ip>:8080/songs}, laedt eine Datei
 * herunter und importiert sie dann in der PWA ("Auf diesem Geraet"). Bewusst
 * KEIN fetch aus der HTTPS-App heraus (das waere Mixed Content) - hier laeuft
 * alles ueber direkte Browser-Navigation.
 *
 * Dateien liegen in karaoke.share.dir (Default ../share relativ zum
 * Arbeitsverzeichnis backend/). Es werden nur Dateien direkt in diesem Ordner
 * ausgeliefert, deren Name auf {@code [A-Za-z0-9._-]+.ksong} passt.
 */
@RestController
public class ShareController {

    private static final Pattern SAFE_NAME = Pattern.compile("[A-Za-z0-9._-]+\\.ksong");
    // "title": "..."  aus dem manifest.json (von ksong.py per json.dumps geschrieben,
    // d.h. " und \ sind als \" bzw. \\ escaped). Reicht fuer Songtitel.
    private static final Pattern TITLE = Pattern.compile(
            "\"title\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"");

    private final Path shareDir;

    public ShareController(@Value("${karaoke.share.dir}") String shareDir) {
        this.shareDir = Path.of(shareDir).toAbsolutePath().normalize();
        try {
            Files.createDirectories(this.shareDir);
        } catch (IOException e) {
            throw new UncheckedIOException("Konnte Share-Ordner nicht anlegen: " + this.shareDir, e);
        }
    }

    private record Entry(String fileName, String title, long size) {
    }

    private List<Entry> listBundles() {
        if (!Files.isDirectory(shareDir)) {
            return List.of();
        }
        List<Entry> out = new ArrayList<>();
        try (var stream = Files.list(shareDir)) {
            stream.filter(Files::isRegularFile)
                    .filter(p -> SAFE_NAME.matcher(p.getFileName().toString()).matches())
                    .forEach(p -> out.add(new Entry(
                            p.getFileName().toString(),
                            readTitle(p, p.getFileName().toString()),
                            sizeOf(p))));
        } catch (IOException e) {
            throw new UncheckedIOException("Konnte Share-Ordner nicht lesen: " + shareDir, e);
        }
        out.sort(Comparator.comparing(e -> e.title().toLowerCase()));
        return out;
    }

    private String readTitle(Path ksong, String fallback) {
        try (ZipFile zf = new ZipFile(ksong.toFile())) {
            ZipEntry manifest = zf.getEntry("manifest.json");
            if (manifest != null) {
                String json = new String(zf.getInputStream(manifest).readAllBytes(), StandardCharsets.UTF_8);
                Matcher m = TITLE.matcher(json);
                if (m.find()) {
                    String title = jsonUnescape(m.group(1));
                    if (!title.isBlank()) {
                        return title;
                    }
                }
            }
        } catch (IOException ignored) {
            // kaputtes / kein ZIP -> Dateiname als Titel
        }
        return fallback.replaceFirst("\\.ksong$", "");
    }

    private static String jsonUnescape(String s) {
        if (s.indexOf('\\') < 0) {
            return s;
        }
        StringBuilder out = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '\\' && i + 1 < s.length()) {
                char n = s.charAt(++i);
                switch (n) {
                    case 'n' -> out.append('\n');
                    case 't' -> out.append('\t');
                    case 'r' -> out.append('\r');
                    case 'u' -> {
                        if (i + 4 < s.length()) {
                            out.append((char) Integer.parseInt(s.substring(i + 1, i + 5), 16));
                            i += 4;
                        }
                    }
                    default -> out.append(n); // \" \\ \/
                }
            } else {
                out.append(c);
            }
        }
        return out.toString();
    }

    private static long sizeOf(Path p) {
        try {
            return Files.size(p);
        } catch (IOException e) {
            return 0L;
        }
    }

    @GetMapping(value = "/songs", produces = MediaType.TEXT_HTML_VALUE + ";charset=UTF-8")
    public String index() {
        StringBuilder sb = new StringBuilder(2048);
        sb.append("""
                <!doctype html><html lang="de"><head><meta charset="utf-8">
                <meta name="viewport" content="width=device-width,initial-scale=1">
                <title>Karaoke-Songs</title><style>
                :root{color-scheme:light dark}
                body{font:16px/1.5 system-ui,sans-serif;margin:0;padding:1.5rem;max-width:40rem}
                h1{font-size:1.3rem;margin:0 0 .25rem}
                p.hint{color:#888;margin:0 0 1.5rem}
                ul{list-style:none;padding:0;margin:0}
                li{margin:.5rem 0}
                a.song{display:flex;justify-content:space-between;gap:1rem;align-items:baseline;
                  padding:.9rem 1rem;border:1px solid #8884;border-radius:.6rem;text-decoration:none;color:inherit}
                a.song:active{background:#8882}
                .sz{color:#888;font-size:.85rem;white-space:nowrap}
                </style></head><body>
                <h1>Karaoke-Songs</h1>
                <p class="hint">Song antippen zum Herunterladen, dann in der App unter
                &bdquo;Auf diesem Ger&auml;t&ldquo; importieren.</p><ul>
                """);
        List<Entry> bundles = listBundles();
        if (bundles.isEmpty()) {
            sb.append("<li><em>Keine Songs im Share-Ordner.</em></li>");
        }
        for (Entry e : bundles) {
            sb.append("<li><a class=\"song\" href=\"/songs/")
                    .append(urlEncode(e.fileName()))
                    .append("\" download><span>")
                    .append(htmlEscape(e.title()))
                    .append("</span><span class=\"sz\">")
                    .append(humanSize(e.size()))
                    .append("</span></a></li>");
        }
        sb.append("</ul></body></html>");
        return sb.toString();
    }

    @GetMapping("/songs/{name}")
    public ResponseEntity<Resource> download(@PathVariable String name) {
        if (!SAFE_NAME.matcher(name).matches()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Ungueltiger Dateiname");
        }
        Path file = shareDir.resolve(name).normalize();
        if (!file.startsWith(shareDir) || !Files.isRegularFile(file)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Song nicht gefunden: " + name);
        }
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("application/zip"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + name + "\"")
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(new FileSystemResource(file));
    }

    private static String htmlEscape(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;");
    }

    private static String urlEncode(String s) {
        return java.net.URLEncoder.encode(s, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private static String humanSize(long bytes) {
        if (bytes >= 1024 * 1024) {
            return String.format("%.1f MB", bytes / 1024.0 / 1024.0);
        }
        return Math.round(bytes / 1024.0) + " KB";
    }
}
