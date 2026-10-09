import { cartQueryOptions } from "#/queries/cart"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import ThemeToggle from "./ThemeToggle"
import { Route } from "#/routes/__root"
import storeIcon from "#/images/storeIcon.png"

export default function Header() {
	const user = Route.useRouteContext().user
	const { data: cart } = useQuery({
		...cartQueryOptions(),
		enabled: !!user,
	})

	return (
		<header className="bg-(--header-bg) px-4 backdrop-blur-lg">
			<nav className="page-wrap max-w-6xl mx-auto flex flex-wrap items-center gap-x-3 gap-y-2 py-3 sm:py-5">
				<div className="m-0 shrink-0 text-base font-semibold tracking-tight flex gap-10">
					<a href="/">
						<img
							src={storeIcon}
							alt="store icon"
							width={64}
							height={64}
							className="invert-(--logo-invert)"
						/>
					</a>
					<div className="flex">
						<a href="/" className="header-nav-e">
							STORE
						</a>
						<Link to="/" className="header-nav-e">
							COMMUNITY
						</Link>
						<Link to="/about" className="header-nav-e">
							ABOUT
						</Link>
					</div>
				</div>

				<div className="ml-auto flex items-center gap-1.5 sm:gap-4">
					{user ? (
						<>
							<Link to="/cart" className="header-nav-e flex items-center gap-1">
								CART
								{cart && cart.length > 0 && (
									<span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-500 px-1 text-xs font-bold text-white">
										{cart.length}
									</span>
								)}
							</Link>
							<Link to="/profile" className="header-nav-e">
								{user.username}
							</Link>
						</>
					) : (
						<Link to="/login" className="header-nav-e">
							sign in
						</Link>
					)}
					<ThemeToggle />
				</div>
			</nav>
		</header>
	)
}
