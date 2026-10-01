import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
	addToCart,
	addToLibrary,
	checkout,
	clearCart,
	removeFromCart,
} from "#/server_functions/cart"
import type {
	CartAddResponse,
	CartClearResponse,
	CartRemoveResponse,
	CheckoutResponse,
	LibraryResponse,
} from "#/server_functions/cart"
import type { ApiResult } from "#/utils/api"

export type { CheckoutResponse }

export class CartError extends Error {
	status: number

	constructor(status: number, message: string) {
		super(message)
		this.name = "CartError"
		this.status = status
	}
}

/**
 * The server functions hand backend failures back as data (so the status code
 * survives the round trip); the UI wants an error carrying that status.
 */
function unwrap<T>(result: ApiResult<T>): T {
	if (!result.ok) {
		throw new CartError(result.status, result.message)
	}
	return result.data
}

export function useAddToCart() {
	const queryClient = useQueryClient()

	return useMutation<CartAddResponse, CartError, number>({
		mutationFn: async (appid) => unwrap(await addToCart({ data: { appid } })),
		onSuccess: () => {
			// Awaited by callers that need the cart to already contain the game
			// (the "added to cart" modal lists the freshly fetched cart).
			return queryClient.invalidateQueries({ queryKey: ["cart"] })
		},
	})
}

export function useRemoveFromCart() {
	const queryClient = useQueryClient()

	return useMutation<CartRemoveResponse, CartError, number>({
		mutationFn: async (appid) =>
			unwrap(await removeFromCart({ data: { appid } })),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cart"] }),
	})
}

export function useClearCart() {
	const queryClient = useQueryClient()

	return useMutation<CartClearResponse, CartError, void>({
		mutationFn: async () => unwrap(await clearCart({ data: {} })),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cart"] }),
	})
}

// Free-to-play games never enter the cart: they go straight to the library.
export function useAddToLibrary() {
	const queryClient = useQueryClient()

	return useMutation<LibraryResponse, CartError, number>({
		mutationFn: async (appid) =>
			unwrap(await addToLibrary({ data: { appid } })),
		onSuccess: () =>
			queryClient.invalidateQueries({ queryKey: ["owned-games"] }),
	})
}

export function useCheckout() {
	const queryClient = useQueryClient()

	return useMutation<CheckoutResponse, CartError, void>({
		mutationFn: async () => unwrap(await checkout({ data: {} })),
		onSuccess: (data) => {
			// Only clear the local cart once the games are actually granted;
			// a redirect to YooKassa keeps the rows until the webhook fires.
			if (!("confirmation_url" in data)) {
				queryClient.invalidateQueries({ queryKey: ["cart"] })
				queryClient.invalidateQueries({ queryKey: ["owned-games"] })
			}
		},
	})
}
