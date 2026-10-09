import type { Game } from "#/types"
import { authMiddleware, PAYMENT_API } from "#/utils/api"
import { queryOptions } from "@tanstack/react-query"
import { createServerFn } from "@tanstack/react-start"

type CartResponse = {
	results: Game[]
}

export const fetchCart = createServerFn({ method: "GET" })
	.middleware([authMiddleware])
	.handler(async ({ context }): Promise<Game[]> => {
		try {
			const response = await context.api(`${PAYMENT_API}/payment/cart`)
			if (!response.ok) {
				throw new Error("Failed to fetch your cart")
			}
			const data: CartResponse = await response.json()
			return data.results
		} catch {
			throw new Error("Failed to fetch your cart")
		}
	})

export const cartQueryOptions = () =>
	queryOptions({
		queryKey: ["cart"],
		queryFn: () => fetchCart(),
	})
