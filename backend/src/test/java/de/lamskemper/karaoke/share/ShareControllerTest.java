package de.lamskemper.karaoke.share;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@ActiveProfiles("test")
class ShareControllerTest {

    static Path shareDir;

    @DynamicPropertySource
    static void shareDirProp(DynamicPropertyRegistry registry) throws IOException {
        shareDir = Files.createTempDirectory("share-test");
        registry.add("karaoke.share.dir", () -> shareDir.toString());
    }

    @Autowired
    WebApplicationContext wac;

    MockMvc mvc;

    @BeforeEach
    void setUp() throws IOException {
        mvc = MockMvcBuilders.webAppContextSetup(wac).build();
        for (Path p : Files.list(shareDir).toList()) {
            Files.deleteIfExists(p);
        }
    }

    private void writeKsong(String fileName, String title) throws IOException {
        Path f = shareDir.resolve(fileName);
        try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(f))) {
            zip.putNextEntry(new ZipEntry("manifest.json"));
            String manifest = "{\n  \"ksongVersion\": 1,\n  \"title\": \"" + title
                    + "\",\n  \"tracks\": []\n}";
            zip.write(manifest.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
            zip.putNextEntry(new ZipEntry("tracks/Gesang/audio.m4a"));
            zip.write(new byte[] {1, 2, 3, 4});
            zip.closeEntry();
        }
    }

    @Test
    void listsBundlesWithTitleFromManifest() throws Exception {
        writeKsong("amazing-grace.ksong", "Amazing Grace");
        writeKsong("umlaut.ksong", "Vom Flügel");

        mvc.perform(get("/songs"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("text/html"))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("Amazing Grace")))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("Vom Flügel")))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("href=\"/songs/amazing-grace.ksong\"")));
    }

    @Test
    void escapesTitleFromManifest() throws Exception {
        writeKsong("weird.ksong", "Rock & <Roll>");

        mvc.perform(get("/songs"))
                .andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.containsString("Rock &amp; &lt;Roll&gt;")))
                .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("<Roll>"))));
    }

    @Test
    void downloadsBundleAsAttachment() throws Exception {
        writeKsong("amazing-grace.ksong", "Amazing Grace");

        mvc.perform(get("/songs/amazing-grace.ksong"))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Disposition", "attachment; filename=\"amazing-grace.ksong\""))
                .andExpect(content().contentType("application/zip"));
    }

    @Test
    void unknownBundleIs404() throws Exception {
        mvc.perform(get("/songs/does-not-exist.ksong")).andExpect(status().isNotFound());
    }

    @Test
    void nonKsongNameIs404() throws Exception {
        Path evil = shareDir.resolve("secret.txt");
        try (OutputStream os = Files.newOutputStream(evil)) {
            os.write("nope".getBytes(StandardCharsets.UTF_8));
        }
        mvc.perform(get("/songs/secret.txt")).andExpect(status().isNotFound());
    }
}
