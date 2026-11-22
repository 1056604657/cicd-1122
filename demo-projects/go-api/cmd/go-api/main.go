package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"

	"example.com/go-api/internal/greeting"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/greet", func(w http.ResponseWriter, r *http.Request) {
		// 用 JSON 编码而不是直接写字符串：直接写 ResponseWriter 会被 semgrep 判为
		// 潜在的响应体注入（浏览器把它当 HTML 时就是 XSS），JSON 编码自带转义，
		// 也是 API 更常规的返回形式。
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		resp := map[string]string{"greeting": greeting.Greet(r.URL.Query().Get("name"))}
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			log.Printf("write response: %v", err)
		}
	})

	log.Printf("go-api listening on %s", port)
	// 这里刻意用明文 HTTP：TLS 在 Ingress 终结，Pod 内再套一层 TLS 等于双重终止，
	// 证书还得在集群内分发。这条规则对"集群内服务"是误报，抑制范围仅限下一行。
	// nosemgrep: go.lang.security.audit.net.use-tls.use-tls
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatalf("server stopped: %v", err)
	}
}
