package de.lamskemper.karaoke.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Erlaubt dem Nuxt-Dev-Server (localhost:3000) Zugriff auf die API (localhost:8080).
 * In Produktion laufen Frontend/Backend hinter Tailscale im selben privaten Netz -
 * Zugriffskontrolle passiert dort ueber die Tailnet-Mitgliedschaft, nicht CORS.
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOriginPatterns("http://localhost:*", "http://100.*.*.*:*")
                .allowedMethods("GET", "POST", "PUT", "DELETE")
                .allowedHeaders("*");
    }
}
