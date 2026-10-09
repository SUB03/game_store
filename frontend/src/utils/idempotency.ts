const STORAGE_KEY = "checkout-idempotency-key"

let memoryFallback: string | null = null

/**
 * One UUID per checkout attempt: stable across retries (double-click,
 * network retry, page reload) of the same cart, but cleared whenever the
 * cart changes or a checkout attempt resolves, so the next attempt gets a
 * fresh key.
 */
export function getOrCreateCheckoutIdempotencyKey(): string {
	try {
		const existing = sessionStorage.getItem(STORAGE_KEY)
		if (existing) return existing
		const key = crypto.randomUUID()
		sessionStorage.setItem(STORAGE_KEY, key)
		return key
	} catch {
		// sessionStorage unavailable (private browsing, disabled storage) -
		// fall back to an in-memory key for the lifetime of this page.
		if (!memoryFallback) memoryFallback = crypto.randomUUID()
		return memoryFallback
	}
}

export function clearCheckoutIdempotencyKey(): void {
	memoryFallback = null
	try {
		sessionStorage.removeItem(STORAGE_KEY)
	} catch {
		// ignore
	}
}
