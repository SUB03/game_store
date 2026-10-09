import GameSelectionItemSmall from "#/components/GameSelectionItemSmall"
import { useLogout } from "#/mutations/auth"
import { ownedGamesQueryOptions } from "#/queries/ownedGames"
import { useSuspenseQuery } from "@tanstack/react-query"
import {
	createFileRoute,
	Link,
	redirect,
	useRouter,
} from "@tanstack/react-router"

export const Route = createFileRoute("/profile")({
	beforeLoad: async ({ context }) => {
		if (!context.user) {
			throw redirect({
				to: "/login",
			})
		}
		return { user: context.user }
	},
	loader: async ({ context }) => {
		return await context.queryClient.query(ownedGamesQueryOptions())
	},
	component: RouteComponent,
})

function RouteComponent() {
	const context = Route.useRouteContext()
	const router = useRouter()
	const logout = useLogout()
	const { data: ownedGames } = useSuspenseQuery(ownedGamesQueryOptions())

	return (
		<main className="page-wrap min-h-175 px-4 pb-8 max-w-6xl mx-auto">
			<div className="flex flex-wrap items-center justify-between gap-4 py-6">
				<h1 className="text-2xl font-semibold text-(--sea-ink)">
					Hello {context.user.username}!
				</h1>
				<button
					className="rounded-xs p-2 blue-button cursor-pointer text-gray-100"
					type="button"
					onClick={async () => {
						await logout.mutateAsync()
						router.invalidate()
					}}
				>
					Logout
				</button>
			</div>

			<h2 className="mb-4 text-lg font-bold tracking-tight text-(--sea-ink)">
				YOUR LIBRARY
			</h2>

			{ownedGames.length === 0 ? (
				<div className="glass-panel shadow_item p-8 text-center">
					<p className="mb-4 text-(--sea-ink-soft)">
						You don't own any games yet.
					</p>
					<Link
						to="/"
						className="inline-block rounded-xs px-4 py-2 font-medium text-gray-100 blue-button"
					>
						Browse the store
					</Link>
				</div>
			) : (
				<div className="flex flex-col gap-2">
					{ownedGames.map((game) => (
						<GameSelectionItemSmall key={game.appid} game={game} />
					))}
				</div>
			)}
		</main>
	)
}
