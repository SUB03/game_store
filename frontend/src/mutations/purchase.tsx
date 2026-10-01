import { useMutation, useQueryClient } from "@tanstack/react-query"
import { purchaseGame } from "#/server_functions/purchase"
import type { PurchaseResponse } from "#/server_functions/purchase"
import type { ApiResult } from "#/utils/api"

export type { PurchaseResponse }

export class PurchaseError extends Error {
	status: number

	constructor(status: number, message: string) {
		super(message)
		this.name = "PurchaseError"
		this.status = status
	}
}

/** Turn the server function's result into data or a `PurchaseError`. */
function unwrap<T>(result: ApiResult<T>): T {
	if (!result.ok) {
		throw new PurchaseError(result.status, result.message)
	}
	return result.data
}

export function usePurchaseGame() {
	const queryClient = useQueryClient()

	return useMutation<PurchaseResponse, PurchaseError, number>({
		mutationFn: async (appid) =>
			unwrap(await purchaseGame({ data: { appid } })),
		onSuccess: (data) => {
			if ("confirmation_url" in data) {
				window.location.assign(data.confirmation_url)
			} else {
				queryClient.invalidateQueries({ queryKey: ["owned-games"] })
			}
		},
		onError: (error) => {
			// The backend already knows we own it - sync the local library.
			if (error instanceof PurchaseError && error.status === 409) {
				queryClient.invalidateQueries({ queryKey: ["owned-games"] })
			}
		},
	})
}
