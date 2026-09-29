import { createMiddleware } from "@tanstack/react-start"
import {
	getCookie,
	getRequestHeader,
	setResponseHeader,
} from "@tanstack/react-start/server"
import axios from "redaxios"

export const AUTH_API =
	process.env.AUTH_SERVICE_URL ??
	(import.meta.env.DEV ? "http://localhost:8000" : "")
export const STORE_API =
	process.env.STORE_SERVICE_URL ??
	(import.meta.env.DEV ? "http://localhost:8001" : "")

export const auth_api = axios.create({
	baseURL: AUTH_API,
	withCredentials: true,
	headers: {
		"Content-Type": "application/json",
	},
})

export const store_api = axios.create({
	baseURL: STORE_API,
	withCredentials: true,
	headers: {
		"Content-Type": "application/json",
	},
})

export const authMiddleware = createMiddleware({ type: "function" }).server(
	async ({ next }) => {
		const cookieHeader = getRequestHeader("cookie")
		const refresh_token = getCookie("refresh_token")

		const proxyCookies = (backendResponse: Response) => {
			const setCookieHeaders = backendResponse.headers.getSetCookie()
			setResponseHeader("Set-Cookie", setCookieHeaders)
		}

		const fetchFromBackend = async (
			urlPath: string,
			options: RequestInit = {},
		): Promise<Response> => {
			const headers = new Headers(options.headers)
			if (cookieHeader) {
				headers.set("cookie", cookieHeader)
			}

			let response = await fetch(urlPath, { ...options, headers })

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
						proxyCookies(refreshResponse)

						const newCookies = refreshResponse.headers.getSetCookie().join("; ")
						if (newCookies) {
							headers.set("cookie", newCookies)
						}

						response = await fetch(urlPath, { ...options, headers })
					}
				} catch (err) {
					console.error(err)
				}
			}
			return response
		}
		return next({
			context: {
				api: fetchFromBackend,
			},
		})
	},
)
