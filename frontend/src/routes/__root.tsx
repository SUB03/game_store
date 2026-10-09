import {
	HeadContent,
	Scripts,
	createRootRouteWithContext,
} from "@tanstack/react-router"
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools"
import { TanStackDevtools } from "@tanstack/react-devtools"
import type { QueryClient } from "@tanstack/react-query"
import Footer from "../components/Footer"
import Header from "../components/Header"

import appCss from "../styles.css?url"
import { ReactQueryDevtoolsPanel } from "@tanstack/react-query-devtools"
import { getUsersMe } from "#/server_functions/getUsersMe"
import { getThemeCookie } from "#/server_functions/theme"

interface MyRouterContext {
	queryClient: QueryClient
}

export const Route = createRootRouteWithContext<MyRouterContext>()({
	beforeLoad: async () => {
		const [user, theme] = await Promise.all([getUsersMe(), getThemeCookie()])

		return { user, theme }
	},
	head: () => ({
		meta: [
			{
				charSet: "utf-8",
			},
			{
				name: "viewport",
				content: "width=device-width, initial-scale=1",
			},
			{
				title: "Store",
			},
		],
		links: [
			{
				rel: "stylesheet",
				href: appCss,
			},
		],
	}),
	shellComponent: RootDocument,
})

function RootDocument({ children }: { children: React.ReactNode }) {
	// Read from the `theme` cookie (set by ThemeToggle) so the server renders
	// the right theme on the very first byte - no flash-of-wrong-theme on
	// load, unlike reading from localStorage (which the server can't see).
	// `null` means a first-ever visit with no cookie yet; ThemeToggle detects
	// the OS preference client-side once and persists it for every load after.
	const theme = Route.useRouteContext().theme ?? "light"

	return (
		<html lang="en" data-theme={theme} style={{ colorScheme: theme }}>
			<head>
				<HeadContent />
			</head>
			<body className="font-sans antialiased wrap-anywhere selection:bg-[rgba(79,184,178,0.24)]">
				<Header />
				{children}
				<Footer />
				{import.meta.env.DEV && (
					<TanStackDevtools
						config={{ position: "bottom-right" }}
						plugins={[
							{
								name: "Tanstack Router",
								render: <TanStackRouterDevtoolsPanel />,
							},
							{
								name: "tanstack Query",
								render: <ReactQueryDevtoolsPanel />,
							},
						]}
					/>
				)}
				<Scripts />
			</body>
		</html>
	)
}
