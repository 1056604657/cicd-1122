package com.example.javaapi;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public final class JavaApiApplication {

    private JavaApiApplication() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            return "Hello, world";
        }
        return "Hello, " + name;
    }

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        server.createContext("/healthz", exchange -> respond(exchange, 200, "ok"));
        server.createContext("/greet", exchange -> respond(exchange, 200, greet(extractName(exchange))));
        server.setExecutor(null);
        server.start();
        System.out.println("java-api listening on " + port);
    }

    private static String extractName(HttpExchange exchange) {
        String query = exchange.getRequestURI().getQuery();
        if (query == null) {
            return "world";
        }
        for (String part : query.split("&")) {
            if (part.startsWith("name=")) {
                return URLDecoder.decode(part.substring("name=".length()), StandardCharsets.UTF_8);
            }
        }
        return "world";
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, payload.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(payload);
        }
    }
}
