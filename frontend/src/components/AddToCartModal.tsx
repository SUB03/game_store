import type { Game } from "#/types"
import { formatCurrencyValue } from "#/utils/currencyFormatter"
import { useNavigate } from "@tanstack/react-router"
import { useEffect } from "react"
import Price from "./Price"

/**
 * Shown right after a game lands in the cart: lists what is currently in the
 * cart (fetched from the server) and offers the two exits.
 */
export default function AddToCartModal({
	games,
	onClose,
}: {
	games: Game[]
	onClose: () => void
}) {
	const navigate = useNavigate()

	const total = games.reduce((sum, game) => sum + game.price, 0)

	useEffect(() => {
		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") {
				onClose()
			}
		}
		window.addEventListener("keydown", handleKeyDown)
		return () => window.removeEventListener("keydown", handleKeyDown)
	}, [onClose])

	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
			{/* the backdrop is a real button so it is dismissible without a mouse */}
			<button
				type="button"
				aria-label="Close the cart dialog"
				onClick={onClose}
				className="absolute inset-0 cursor-default"
			/>
			<div
				className="glass-panel shadow_item relative w-full max-w-lg p-4"
				role="dialog"
				aria-modal="true"
				aria-label="Added to your cart"
			>
				<div className="mb-3 flex items-center justify-between">
					<h2 className="text-lg font-bold text-(--sea-ink)">
						Added to your cart
					</h2>
					<span className="text-sm text-(--sea-ink-soft)">
						{games.length} {games.length === 1 ? "item" : "items"}
					</span>
				</div>

				<ul className="mb-4 flex max-h-80 flex-col gap-2 overflow-y-auto">
					{games.map((game) => (
						<li
							key={game.appid}
							className="flex items-center gap-3 rounded-md bg-(--inset-glint) p-2"
						>
							<img
								src={game.header_image}
								alt={game.name}
								className="h-12 w-20 shrink-0 rounded-xs object-cover"
							/>
							<a
								href={`/app/${game.appid}/${game.name}`}
								className="grow truncate text-sm font-semibold hover:underline"
							>
								{game.name}
							</a>
							<div className="shrink-0 text-sm">
								<Price
									price={game.price}
									discount={game.discount}
									undiscounted_price={null}
								/>
							</div>
						</li>
					))}
				</ul>

				<div className="mb-4 flex items-center justify-between border-t border-(--chip-line) pt-3">
					<span className="text-sm font-semibold text-(--sea-ink)">Total</span>
					<span className="font-bold text-(--sea-ink)">
						{formatCurrencyValue({ value: total, locale: "us" })}
					</span>
				</div>

				<div className="flex flex-wrap justify-end gap-2">
					<button
						type="button"
						onClick={onClose}
						className="rounded-xs border border-(--chip-line) px-6 py-3 font-semibold text-(--sea-ink) cursor-pointer"
					>
						Continue shopping
					</button>
					<button
						type="button"
						onClick={() => {
							onClose()
							navigate({ to: "/cart" })
						}}
						className="rounded-xs px-6 py-3 font-medium text-gray-100 blue-button cursor-pointer"
					>
						Go to cart
					</button>
				</div>
			</div>
		</div>
	)
}
