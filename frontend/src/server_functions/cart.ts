import type { ApiResult } from "#/utils/api"
import { authMiddleware, callPayment } from "#/utils/api"
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
 * `payment_service` or on a reverse proxy in front of the app.
 */
export const addToCart = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(appidInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<CartAddResponse>> =>
			callPayment<CartAddResponse>(context, "/payment/cart", {
				method: "POST",
				body: JSON.stringify(data),
			}),
	)

export const removeFromCart = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(appidInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<CartRemoveResponse>> =>
			callPayment<CartRemoveResponse>(context, `/payment/cart/${data.appid}`, {
				method: "DELETE",
			}),
	)

export const clearCart = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(emptyInput)
	.handler(
		async ({ context }): Promise<ApiResult<CartClearResponse>> =>
			callPayment<CartClearResponse>(context, "/payment/cart", {
				method: "DELETE",
			}),
	)

export const addToLibrary = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(appidInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<LibraryResponse>> =>
			callPayment<LibraryResponse>(context, "/payment/library", {
				method: "POST",
				body: JSON.stringify(data),
			}),
	)

export const checkout = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(emptyInput)
	.handler(
		async ({ context }): Promise<ApiResult<CheckoutResponse>> =>
			callPayment<CheckoutResponse>(context, "/payment/checkout", {
				method: "POST",
				body: JSON.stringify({}),
			}),
	)
