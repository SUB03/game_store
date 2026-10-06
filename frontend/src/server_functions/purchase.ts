import type { ApiResult } from "#/utils/api"
import { authMiddleware, callPayment } from "#/utils/api"
import { createServerFn } from "@tanstack/react-start"
import z from "zod"

export type PurchaseRedirect = {
	payment_id: string
	confirmation_url: string
}

export type PurchaseGranted = {
	message: string
	appid: number
}

export type PurchaseResponse = PurchaseRedirect | PurchaseGranted

const appidInput = z.object({ appid: z.number().int() })

/** Single-game purchase; the cart flow goes through `checkout` instead. */
export const purchaseGame = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(appidInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<PurchaseResponse>> =>
			callPayment<PurchaseResponse>(context, "/payment/purchase_game", {
				method: "POST",
				body: JSON.stringify(data),
			}),
	)
