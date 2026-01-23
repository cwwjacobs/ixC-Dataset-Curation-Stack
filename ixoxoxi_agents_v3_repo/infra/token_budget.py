class TokenBudgetEnforcer:
    """
    Enforces token limits on context injection and triggers summarization.
    """
    def __init__(self, max_tokens=8000, warn_ratio=0.7, critical_ratio=0.85):
        self.max_tokens = max_tokens
        self.warn_ratio = warn_ratio
        self.critical_ratio = critical_ratio

    def estimate_tokens(self, text: str) -> int:
        # Rough heuristic: 4 chars/token
        return max(1, len(text) // 4)

    def check(self, context_text: str):
        used = self.estimate_tokens(context_text)
        ratio = used / self.max_tokens

        if ratio >= self.critical_ratio:
            return "critical", used, ratio
        if ratio >= self.warn_ratio:
            return "warning", used, ratio
        return "ok", used, ratio
