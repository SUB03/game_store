import { useEffect, useState } from "react"
import { Route } from "#/routes/__root"
import { setThemeCookie, type ThemeMode } from "#/server_functions/theme"

function applyThemeMode(mode: ThemeMode) {
	document.documentElement.setAttribute("data-theme", mode)
	document.documentElement.style.colorScheme = mode
}

export default function ThemeToggle() {
	// The server already resolved this from the `theme` cookie and rendered
	// the matching data-theme attribute, so there is nothing to apply here
	// on a normal load - only the toggle and the first-ever-visit fallback
	// below ever touch the DOM directly.
	const serverTheme = Route.useRouteContext().theme
	const [mode, setMode] = useState<ThemeMode>(serverTheme ?? "light")

	// Only ever run this resolution once, on mount - `serverTheme` is read
	// just to decide whether to run at all, not to react to changes.
	// biome-ignore lint/correctness/useExhaustiveDependencies: intentional mount-only effect
	useEffect(() => {
		if (serverTheme) {
			return
		}
		// First-ever visit: no cookie yet, so the server rendered the CSS
		// default ("light"). Resolve the OS preference once, client-side,
		// and persist it so every load after this one is flicker-free too.
		const preferred: ThemeMode = window.matchMedia(
			"(prefers-color-scheme: dark)",
		).matches
			? "dark"
			: "light"
		if (preferred !== "light") {
			setMode(preferred)
			applyThemeMode(preferred)
		}
		setThemeCookie({ data: { mode: preferred } })
	}, [])

	function toggleMode() {
		const nextMode: ThemeMode = mode === "light" ? "dark" : "light"
		setMode(nextMode)
		applyThemeMode(nextMode)
		setThemeCookie({ data: { mode: nextMode } })
	}

	const label = `Theme mode: ${mode}. Click to switch to ${
		mode === "light" ? "dark" : "light"
	} mode.`

	return (
		<button
			type="button"
			onClick={toggleMode}
			aria-label={label}
			title={label}
			className="rounded-full border border-(--chip-line) bg-(--chip-bg) px-3 py-1.5 text-sm font-semibold text-(--sea-ink) shadow-[0_8px_22px_rgba(30,90,72,0.08)] transition hover:-translate-y-0.5"
		>
			{mode === "dark" ? "Dark" : "Light"}
		</button>
	)
}
