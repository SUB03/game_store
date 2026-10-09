import type { Game } from "#/types"
import { store_api } from "#/utils/api"
import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query"
import { createServerFn } from "@tanstack/react-start"
import z from "zod"

const gamesParamsSchema = z.object({
	offset: z.number().int().nonnegative(),
	search: z.string().optional(),
	tags: z.array(z.string()).optional(),
})

type GamesRespose = {
	results: Game[]
	is_next_page: boolean
}

type GamesParams = {
	offset: number
	search?: string
	tags?: string[]
}

type GamesFilters = Omit<GamesParams, "offset">

export const fetchGames = createServerFn({ method: "GET" })
	.validator(gamesParamsSchema)
	.handler(async ({ data }) => {
		try {
			const response = await store_api.get<GamesRespose>("store/games", {
				params: data,
			})
			return response.data
		} catch {
			throw new Error("Failed to fetch games")
		}
	})

export const gamesQueryOptions = (params: GamesParams) =>
	queryOptions({
		queryKey: ["games", "head", params],
		queryFn: () => fetchGames({ data: params }),
	})

export const gamesInfiniteQueryOptions = (
	offset: number,
	filters?: GamesFilters,
) =>
	infiniteQueryOptions({
		queryKey: ["games", "tail", offset, filters],
		queryFn: ({ pageParam }) =>
			fetchGames({ data: { offset: pageParam, ...filters } }),
		initialPageParam: offset,
		getNextPageParam: (lastPage, _, lastPageParam) =>
			lastPage.is_next_page ? lastPageParam + 12 : undefined,
	})
