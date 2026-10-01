import type { ApiResult } from "#/utils/api"
import { authMiddleware, callStore } from "#/utils/api"
import { createServerFn } from "@tanstack/react-start"
import z from "zod"

export type CartAddResponse = {
	appid: number
	added: boolean
}

export type CartRemoveResponse = {
	appid: number
	removed: boolean
}

export type CartClearResponse = {
	removed: number
}

export type LibraryResponse = {
	appid: number
	added: boolean
}

export type CheckoutRedirect = {
	payment_id: string
	confirmation_url: string
}

export type CheckoutGranted = {
	message: string
	appids: number[]
}

export type CheckoutResponse = CheckoutRedirect | CheckoutGranted

const appidInput = z.object({ appid: z.number().int() })
const emptyInput = z.object({})

/**
 * Cart mutations are server functions: the browser posts to this app and the
 * request continues from here, inside the Docker network and with the user's
 * cookies, so nothing depends on the visitor being able to reach
 * `store_service` or on a reverse proxy in front of the app.
 */
export const addToCart = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(appidInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<CartAddResponse>> =>
			callStore<CartAddResponse>(context, "/store/cart", {
				method: "POST",
				body: JSON.stringify(data),
			}),
	)

export const removeFromCart = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(appidInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<CartRemoveResponse>> =>
			callStore<CartRemoveResponse>(context, `/store/cart/${data.appid}`, {
				method: "DELETE",
			}),
	)

export const clearCart = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(emptyInput)
	.handler(
		async ({ context }): Promise<ApiResult<CartClearResponse>> =>
			callStore<CartClearResponse>(context, "/store/cart", {
				method: "DELETE",
			}),
	)

export const addToLibrary = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(appidInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<LibraryResponse>> =>
			callStore<LibraryResponse>(context, "/store/library", {
				method: "POST",
				body: JSON.stringify(data),
			}),
	)

export const checkout = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(emptyInput)
	.handler(
		async ({ context }): Promise<ApiResult<CheckoutResponse>> =>
			callStore<CheckoutResponse>(context, "/store/checkout", {
				method: "POST",
				body: JSON.stringify({}),
			}),
	)
