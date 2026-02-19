package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"
)

var (
	orderServiceURL   = getEnv("ORDER_SERVICE_URL", "http://order-service:8081")
	productServiceURL = getEnv("PRODUCT_SERVICE_URL", "http://product-service:8082")
	port              = getEnv("PORT", "8080")
	httpClient        = &http.Client{Timeout: 5 * time.Second}
)

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

type HealthResponse struct {
	Status    string `json:"status"`
	Service   string `json:"service"`
	Timestamp string `json:"timestamp"`
}

type StatusResponse struct {
	Frontend string `json:"frontend"`
	Orders   string `json:"orders"`
	Products string `json:"products"`
}

func healthzHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(HealthResponse{
		Status:    "healthy",
		Service:   "frontend",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	})
}

func readyzHandler(w http.ResponseWriter, r *http.Request) {
	// Check downstream dependencies
	ordersOk := checkService(orderServiceURL + "/healthz")
	productsOk := checkService(productServiceURL + "/healthz")

	if !ordersOk || !productsOk {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"status": "not ready"})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ready"})
}

func checkService(url string) bool {
	resp, err := httpClient.Get(url)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

func statusHandler(w http.ResponseWriter, r *http.Request) {
	status := StatusResponse{Frontend: "ok"}

	if checkService(orderServiceURL + "/healthz") {
		status.Orders = "ok"
	} else {
		status.Orders = "unreachable"
	}

	if checkService(productServiceURL + "/healthz") {
		status.Products = "ok"
	} else {
		status.Products = "unreachable"
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

func proxyHandler(targetBase string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		targetURL := targetBase + r.URL.Path
		if r.URL.RawQuery != "" {
			targetURL += "?" + r.URL.RawQuery
		}

		proxyReq, err := http.NewRequestWithContext(r.Context(), r.Method, targetURL, r.Body)
		if err != nil {
			http.Error(w, "Failed to create request", http.StatusInternalServerError)
			return
		}
		proxyReq.Header = r.Header.Clone()

		resp, err := httpClient.Do(proxyReq)
		if err != nil {
			http.Error(w, "Service unavailable", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()

		for k, v := range resp.Header {
			for _, val := range v {
				w.Header().Add(k, val)
			}
		}
		w.WriteHeader(resp.StatusCode)
		io.Copy(w, resp.Body)
	}
}

func rootHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"service": "frontend",
		"version": "1.0.0",
		"message": "GKE GitOps Platform - Frontend Service",
	})
}

func main() {
	mux := http.NewServeMux()

	mux.HandleFunc("/", rootHandler)
	mux.HandleFunc("/healthz", healthzHandler)
	mux.HandleFunc("/readyz", readyzHandler)
	mux.HandleFunc("/status", statusHandler)
	mux.HandleFunc("/version", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"version": "1.1.0", "service": "frontend"}`)
	})
	mux.HandleFunc("/api/orders/", proxyHandler(orderServiceURL))
	mux.HandleFunc("/api/products/", proxyHandler(productServiceURL))

	server := &http.Server{
		Addr:         fmt.Sprintf(":%s", port),
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  30 * time.Second,
	}

	log.Printf("Frontend service starting on port %s", port)
	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
