import BuyPanel from "#/components/BuyPanel"
import { cartQueryOptions } from "#/queries/cart"
import { gameQueryOptions } from "#/queries/game"
import { ownedGamesQueryOptions } from "#/queries/ownedGames"
import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/app/$appid/$title")({
	component: RouteComponent,
	loader: async ({ context, params }) => {
		const game = await context.queryClient.query(
			gameQueryOptions({ appid: params.appid }),
		)
		if (context.user) {
			await Promise.all([
				context.queryClient.query(ownedGamesQueryOptions()),
				context.queryClient.query(cartQueryOptions()),
			])
		}
		if (!game) {
			throw redirect({
				to: "/",
			})
		}
		return game
	},
})

function RouteComponent() {
	const game = Route.useLoaderData()

	if (!game) {
		throw redirect({
			to: "/",
		})
	}

	return (
		<main className="page-wrap flex flex-col gap-4 px-4 pb-8 max-w-6xl mx-auto">
			<img src={game.header_image} alt={game.name} />
			<BuyPanel game={game} />
			<div>{game.detailed_description}</div>
		</main>
	)
}
