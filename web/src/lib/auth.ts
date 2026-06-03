const TOKEN_KEY = "dipeen_token";

export const auth = {
  getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(TOKEN_KEY);
  },
  setToken(token: string) {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  },
  logout() {
    if (typeof window === "undefined") return;
    this.clearToken();
    localStorage.removeItem("dipeen_user_name");
    window.location.href = "/login";
  },
  isAuthenticated(): boolean {
    if (typeof window === "undefined") return false;
    return !!localStorage.getItem(TOKEN_KEY);
  },
};
