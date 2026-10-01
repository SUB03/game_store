import { useMutation } from "@tanstack/react-query"
import { login, logout, register } from "#/server_functions/auth"
import type { AuthResponse } from "#/server_functions/auth"
import type { ApiResult } from "#/utils/api"

type Credentials = { username: string; password: string }
type RegisterInput = Credentials & { email: string }

export class AuthError extends Error {
	status: number

	constructor(status: number, message: string) {
		super(message)
		this.name = "AuthError"
		this.status = status
	}
}

/** Turn the server function's result into data or an `AuthError`. */
function unwrap<T>(result: ApiResult<T>): T {
	if (!result.ok) {
		throw new AuthError(result.status, result.message)
	}
	return result.data
}

export function useLogin() {
	return useMutation<AuthResponse, AuthError, Credentials>({
		mutationFn: async ({ username, password }) =>
			unwrap(await login({ data: { username, password } })),
	})
}

export function useRegister() {
	return useMutation<AuthResponse, AuthError, RegisterInput>({
		mutationFn: async (input) => unwrap(await register({ data: input })),
	})
}

export function useLogout() {
	return useMutation<{ message: string }, AuthError, void>({
		mutationFn: async () => unwrap(await logout({ data: {} })),
	})
}
