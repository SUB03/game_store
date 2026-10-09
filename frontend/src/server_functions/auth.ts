import type { ApiResult } from "#/utils/api"
import { authMiddleware, callAuth } from "#/utils/api"
import { createServerFn } from "@tanstack/react-start"
import z from "zod"

export type AuthResponse = {
	message: string
	CSRF: string
}

const credentialsInput = z.object({
	username: z.string().min(1),
	password: z.string().min(1),
})

const registerInput = credentialsInput.extend({
	email: z.email(),
})

/**
 * Sign-in happens here rather than in the browser so that the `Set-Cookie`
 * headers of the auth service can be replayed onto this origin by
 * `authMiddleware` - a cross-origin call from the browser could neither read
 * nor store them.
 */
export const login = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(credentialsInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<AuthResponse>> =>
			callAuth<AuthResponse>(context, "/users/login", {
				method: "POST",
				headers: { "Content-Type": "application/x-www-form-urlencoded" },
				body: new URLSearchParams(data).toString(),
			}),
	)

export const register = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(registerInput)
	.handler(
		async ({ data, context }): Promise<ApiResult<AuthResponse>> =>
			callAuth<AuthResponse>(context, "/users/registrate", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(data),
			}),
	)

export const logout = createServerFn({ method: "POST" })
	.middleware([authMiddleware])
	.validator(z.object({}))
	.handler(
		async ({ context }): Promise<ApiResult<{ message: string }>> =>
			callAuth<{ message: string }>(context, "/users/logout", {
				method: "POST",
			}),
	)
