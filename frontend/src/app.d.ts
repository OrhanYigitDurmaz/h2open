// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
import type { UserView } from '#lib/api.js';

declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			/** The logged-in user, or null. Set by hooks.server.ts. */
			user: UserView | null;
			/** Their login token, from the httpOnly session cookie. */
			token: string | null;
		}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
