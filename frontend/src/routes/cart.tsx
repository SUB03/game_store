import GameSelectionItemSmall from "#/components/GameSelectionItemSmall"
import { useCheckout, useRemoveFromCart } from "#/mutations/cart"
import { cartQueryOptions } from "#/queries/cart"
import { formatCurrencyValue } from "#/utils/currencyFormatter"
import { useSuspenseQuery } from "@tanstack/react-query"
import {
	createFileRoute,
	Link,
	redirect,
	useRouter,
} from "@tanstack/react-router"

export const Route = createFileRoute("/cart")({
	beforeLoad: async ({ context }) => {
		if (!context.user) {
			throw redirect({
				to: "/login",
				search: { redirect: "/cart" },
			})
		}
		return { user: context.user }
	},
	loader: async ({ context }) => {
		return await context.queryClient.query(cartQueryOptions())
	},
	component: RouteComponent,
})

function RouteComponent() {
	const router = useRouter()
	const { data: cart } = useSuspenseQuery(cartQueryOptions())
	const remove = useRemoveFromCart()
	const checkout = useCheckout()

	const total = cart.reduce((sum, game) => sum + game.price, 0)

	const proceedToPayment = async () => {
		try {
			const data = await checkout.mutateAsync()
			if ("confirmation_url" in data) {
				window.location.assign(data.confirmation_url)
				return
			}
			// free games were granted immediately - show them in the library
			await router.navigate({ to: "/profile" })
		} catch {
			// CartError is rendered below
		}
	}

	return (
		<main className="page-wrap min-h-175 px-4 pb-8 max-w-6xl mx-auto">
			<div className="flex flex-wrap items-center justify-between gap-4 py-6">
				<h1 className="text-2xl font-semibold text-(--sea-ink)">YOUR CART</h1>
				<Link
					to="/"
					className="rounded-xs border border-(--chip-line) px-4 py-2 font-medium text-(--sea-ink)"
				>
					Continue shopping
				</Link>
			</div>

			{cart.length === 0 ? (
				<div className="glass-panel shadow_item p-8 text-center">
					<p className="mb-4 text-(--sea-ink-soft)">Your cart is empty.</p>
					<Link
						to="/"
						className="inline-block rounded-xs px-4 py-2 font-medium text-gray-100 blue-button"
					>
						Browse the store
					</Link>
				</div>
			) : (
				<>
					<div className="mb-6 flex flex-col gap-2">
						{cart.map((game) => (
							<div key={game.appid} className="flex items-start gap-2">
								<div className="grow">
									<GameSelectionItemSmall game={game} />
								</div>
								<button
									type="button"
									disabled={remove.isPending && remove.variables === game.appid}
									onClick={() => remove.mutate(game.appid)}
									className="shrink-0 rounded-xs border border-(--chip-line) px-3 py-2 text-sm font-medium text-(--sea-ink) cursor-pointer disabled:opacity-60"
								>
									{remove.isPending && remove.variables === game.appid
										? "Removing…"
										: "Remove"}
								</button>
							</div>
						))}
					</div>

					<div className="glass-panel shadow_item flex flex-col gap-4 p-4">
						<div className="flex items-center justify-between">
							<span className="text-lg font-semibold text-(--sea-ink)">
								Total
							</span>
							<span className="text-lg font-bold text-(--sea-ink)">
								{formatCurrencyValue({ value: total, locale: "us" })}
							</span>
						</div>

						{checkout.error && (
							<p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
								{checkout.error.message}
							</p>
						)}

						<div className="flex flex-wrap justify-end gap-2">
							<Link
								to="/"
								className="rounded-xs border border-(--chip-line) px-6 py-3 font-semibold text-(--sea-ink)"
							>
								Continue shopping
							</Link>
							<button
								type="button"
								disabled={checkout.isPending}
								onClick={proceedToPayment}
								className="rounded-xs px-6 py-3 font-medium text-gray-100 blue-button cursor-pointer disabled:opacity-60"
							>
								{checkout.isPending ? "Processing…" : "Proceed to payment"}
							</button>
						</div>
					</div>
				</>
			)}
		</main>
	)
}
