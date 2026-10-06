import { createMiddleware } from "@tanstack/react-start"
import {
	getCookie,
	getRequestHeader,
	setResponseHeader,
} from "@tanstack/react-start/server"
import axios from "redaxios"

export const AUTH_API = process.env.AUTH_SERVICE_URL ?? "http://localhost:8000"
export const STORE_API =
	process.env.STORE_SERVICE_URL ?? "http://localhost:8001"
export const PAYMENT_API =
	process.env.PAYMENT_SERVICE_URL ?? "http://localhost:8002"

/** Result of a server function: either the payload or the backend's error. */
export type ApiResult<T> =
	| { ok: true; data: T }
	| { ok: false; status: number; message: string }

/** The fetch implementation `authMiddleware` hands to server functions. */
export type BackendFetch = (
	urlPath: string,
	options?: RequestInit,
) => Promise<Response>

/**
 * What a server function context must provide to call a backend service.
 *
 * Reading cookies may only ever happen inside the `.server()` callback of
 * `authMiddleware`: the Start compiler strips those callbacks from the client
 * bundle, while any other use of `@tanstack/react-start/server` in a
 * client-reachable module fails `npm run build` with an import-protection
 * error. The cookies are read there once and handed to handlers as context.
 */
export type BackendContext = {
	api: BackendFetch
	csrf: string | undefined
}

/**
 * Server-side client for the public store endpoints. Private data goes through
 * `authMiddleware` instead, which is the only place that can forward cookies.
 */
export const store_api = axios.create({
	baseURL: STORE_API,
	headers: {
		"Content-Type": "application/json",
	},
})

/** Turn a failed backend response into a message safe to show to the user. */
export async function readErrorMessage(response: Response): Promise<string> {
	try {
		const body = (await response.json()) as { detail?: unknown }
		if (typeof body?.detail === "string") {
			return body.detail
		}
	} catch {
		// not a JSON body (HTML error page, empty body)
	}
	return `Request failed with status ${response.status}`
}

/** Call a store endpoint the way the browser cannot: from here, with cookies. */
export async function callStore<T>(
	context: BackendContext,
	path: string,
	init: RequestInit = {},
): Promise<ApiResult<T>> {
	try {
		const headers = new Headers(init.headers)
		headers.set("Content-Type", "application/json")
		// The store endpoints compare this header with the access token's `jti`;
		// the auth service mirrors that value into the non-httponly CSRF cookie.
		headers.set("CSRF", context.csrf ?? "")

		const response = await context.api(`${STORE_API}${path}`, {
			...init,
			headers,
		})
		if (!response.ok) {
			return {
				ok: false,
				status: response.status,
				message: await readErrorMessage(response),
			}
		}
		return { ok: true, data: (await response.json()) as T }
	} catch (err) {
		console.error(err)
		return {
			ok: false,
			status: 0,
			message: "Could not reach the store service",
		}
	}
}

/** Call a payment endpoint (cart, checkout, purchase) with cookies and CSRF. */
export async function callPayment<T>(
	context: BackendContext,
	path: string,
	init: RequestInit = {},
): Promise<ApiResult<T>> {
	try {
		const headers = new Headers(init.headers)
		headers.set("Content-Type", "application/json")
		// The payment endpoints compare this header with the access token's `jti`;
		// the auth service mirrors that value into the non-httponly CSRF cookie.
		headers.set("CSRF", context.csrf ?? "")

		const response = await context.api(`${PAYMENT_API}${path}`, {
			...init,
			headers,
		})
		if (!response.ok) {
			return {
				ok: false,
				status: response.status,
				message: await readErrorMessage(response),
			}
		}
		return { ok: true, data: (await response.json()) as T }
	} catch (err) {
		console.error(err)
		return {
			ok: false,
			status: 0,
			message: "Could not reach the payment service",
		}
	}
}

/** Call an auth endpoint (no CSRF: the auth service does not require it). */
export async function callAuth<T>(
	context: BackendContext,
	path: string,
	init: RequestInit = {},
): Promise<ApiResult<T>> {
	try {
		const response = await context.api(`${AUTH_API}${path}`, init)
		if (!response.ok) {
			return {
				ok: false,
				status: response.status,
				message: await readErrorMessage(response),
			}
		}
		return { ok: true, data: (await response.json()) as T }
	} catch (err) {
		console.error(err)
		return { ok: false, status: 0, message: "Could not reach the auth service" }
	}
}

export const authMiddleware = createMiddleware({ type: "function" }).server(
	async ({ next }) => {
		const cookieHeader = getRequestHeader("cookie")
		const refresh_token = getCookie("refresh_token")

		const fetchFromBackend = async (
			urlPath: string,
			options: RequestInit = {},
		): Promise<Response> => {
			const headers = new Headers(options.headers)
			if (cookieHeader) {
				headers.set("cookie", cookieHeader)
			}

			const cookies: string[] = []

			let response = await fetch(urlPath, { ...options, headers })
			cookies.push(...response.headers.getSetCookie())

			if (response.status === 401 && refresh_token) {
				try {
					const refreshResponse = await fetch(`${AUTH_API}/users/refresh`, {
						method: "POST",
						headers: {
							Cookie: `refresh_token=${refresh_token}`,
							"Content-Type": "application/json",
						},
					})

					if (refreshResponse.ok) {
						cookies.push(...refreshResponse.headers.getSetCookie())

						const newCookies = refreshResponse.headers.getSetCookie().join("; ")
						if (newCookies) {
							headers.set("cookie", newCookies)
						}

						response = await fetch(urlPath, { ...options, headers })
						cookies.push(...response.headers.getSetCookie())
					}
				} catch (err) {
					console.error(err)
				}
			}

			if (cookies.length > 0) {
				setResponseHeader("Set-Cookie", cookies)
			}
			return response
		}
		return next({
			context: {
				api: fetchFromBackend,
				csrf: getCookie("CSRF"),
			},
		})
	},
)
