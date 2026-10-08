window.API_BASE = ["localhost", "127.0.0.1"].includes(window.location.hostname)
  ? "http://localhost:8001/api/v1"
  : "https://military-defense-news-api.onrender.com/api/v1";
