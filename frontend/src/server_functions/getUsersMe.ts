import type { User } from "#/types"
import { AUTH_API, authMiddleware } from "#/utils/api"
import { createServerFn } from "@tanstack/react-start"

export const getUsersMe = createServerFn()
	.middleware([authMiddleware])
	.handler(async ({ context }): Promise<User | null> => {
		const response = await context.api(`${AUTH_API}/users/me`)

		if (!response.ok) {
			return null
		}
		return response.json()
	})
