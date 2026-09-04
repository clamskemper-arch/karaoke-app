package de.lamskemper.karaoke.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * CORS fuer die getrennt gehostete Frontend-App. Erlaubte Origins kommen aus
 * karaoke.cors.allowed-origins (kommagetrennt, Wildcards wie bei
 * allowedOriginPatterns erlaubt) - Default deckt lokalen Dev, das Tailnet
 * (100.* / *.ts.net) und die GitHub-Pages-App ab, siehe application.properties.
 * Im Tailnet uebernimmt die Zugriffskontrolle ohnehin die Tailnet-Mitgliedschaft.
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final String[] allowedOrigins;

    public WebConfig(@Value("${karaoke.cors.allowed-origins}") String allowedOrigins) {
        this.allowedOrigins = allowedOrigins.split("\\s*,\\s*");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOriginPatterns(allowedOrigins)
                .allowedMethods("GET", "POST", "PUT", "DELETE")
                .allowedHeaders("*");
    }
}
