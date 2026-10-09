import { createServerFn } from "@tanstack/react-start"
import { getCookie, setCookie } from "@tanstack/react-start/server"
import z from "zod"

export type ThemeMode = "light" | "dark"

const THEME_COOKIE = "theme"
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365

/** Read during SSR so the server can render the right theme on first paint. */
export const getThemeCookie = createServerFn({ method: "GET" }).handler(
	async (): Promise<ThemeMode | null> => {
		const value = getCookie(THEME_COOKIE)
		return value === "light" || value === "dark" ? value : null
	},
)

const themeInput = z.object({ mode: z.enum(["light", "dark"]) })

export const setThemeCookie = createServerFn({ method: "POST" })
	.validator(themeInput)
	.handler(async ({ data }) => {
		setCookie(THEME_COOKIE, data.mode, {
			maxAge: ONE_YEAR_SECONDS,
			path: "/",
			sameSite: "lax",
		})
	})
