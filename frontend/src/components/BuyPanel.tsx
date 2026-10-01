import { useAddToCart, useAddToLibrary } from "#/mutations/cart"
import type { CartError } from "#/mutations/cart"
import { cartQueryOptions } from "#/queries/cart"
import { ownedGamesQueryOptions } from "#/queries/ownedGames"
import { Route } from "#/routes/__root"
import type { Game } from "#/types"
import { useSuspenseQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useState } from "react"
import AddToCartModal from "./AddToCartModal"
import Price from "./Price"

export default function BuyPanel({ game }: { game: Game }) {
	const user = Route.useRouteContext().user

	if (!user) {
		return <SignInToBuy game={game} />
	}
	return <PurchaseControls game={game} />
}

function gamePath(game: Game) {
	return `/app/${game.appid}/${game.name}`
}

function priceProps(game: Game) {
	const undiscounted_price =
		game.discount > 0 ? game.price * (2 - game.discount / 100) : null
	return { price: game.price, discount: game.discount, undiscounted_price }
}

function SignInToBuy({ game }: { game: Game }) {
	return (
		<div className="glass-panel shadow_item flex flex-wrap items-center justify-between gap-4 p-4">
			<Price {...priceProps(game)} />
			<Link
				to="/login"
				search={{ redirect: gamePath(game) }}
				className="rounded-xs px-6 py-3 font-medium text-gray-100 blue-button"
			>
				Sign in to purchase
			</Link>
		</div>
	)
}

function PurchaseControls({ game }: { game: Game }) {
	const { data: ownedGames } = useSuspenseQuery(ownedGamesQueryOptions())
	const { data: cart } = useSuspenseQuery(cartQueryOptions())
	const addToCart = useAddToCart()
	const addToLibrary = useAddToLibrary()
	const [showCartModal, setShowCartModal] = useState(false)

	const owned = ownedGames.some((g) => g.appid === game.appid)
	const inCart = cart.some((g) => g.appid === game.appid)
	const isFree = game.price <= 0
	const addError: CartError | null = addToCart.error ?? addToLibrary.error

	return (
		<div className="glass-panel shadow_item flex flex-wrap items-center justify-between gap-4 p-4">
			<Price {...priceProps(game)} />
			<div className="flex flex-col items-end gap-2">
				{owned ? (
					<Link
						to="/profile"
						className="rounded-xs border border-(--chip-line) px-6 py-3 font-semibold text-(--sea-ink)"
					>
						In your library
					</Link>
				) : isFree ? (
					<button
						type="button"
						disabled={addToLibrary.isPending}
						onClick={() => addToLibrary.mutate(game.appid)}
						className="rounded-xs px-6 py-3 font-medium text-gray-100 blue-button disabled:opacity-60"
					>
						{addToLibrary.isPending ? "Adding…" : "Add to library"}
					</button>
				) : inCart ? (
					<Link
						to="/cart"
						className="rounded-xs border border-(--chip-line) px-6 py-3 font-semibold text-(--sea-ink)"
					>
						In cart
					</Link>
				) : (
					<button
						type="button"
						disabled={addToCart.isPending}
						onClick={async () => {
							try {
								// resolves only after the ["cart"] invalidation
								// finished, so the modal lists the fresh cart
								await addToCart.mutateAsync(game.appid)
								setShowCartModal(true)
							} catch {
								// CartError is rendered below
							}
						}}
						className="rounded-xs px-6 py-3 font-medium text-gray-100 blue-button disabled:opacity-60"
					>
						{addToCart.isPending ? "Adding…" : "Add to cart"}
					</button>
				)}
				{addError && !owned && (
					<p className="rounded-md bg-red-50 px-3 py-2 text-end text-sm text-red-700">
						{addError.message}
						{addError.status === 401 && (
							<>
								{" "}
								<Link
									to="/login"
									search={{ redirect: gamePath(game) }}
									className="underline"
								>
									Sign in
								</Link>
							</>
						)}
					</p>
				)}
			</div>
			{showCartModal && (
				<AddToCartModal games={cart} onClose={() => setShowCartModal(false)} />
			)}
		</div>
	)
}
