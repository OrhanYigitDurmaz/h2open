import { error, redirect } from '@sveltejs/kit';
import type { Handle } from '@sveltejs/kit/hooks';
import type { Actor } from '#lib/api.js';
import { send, SESSION_COOKIE } from '#lib/server/backend.js';

/** Find who is logged in; keep everyone else out of the (app) routes. */
export const handle: Handle = async ({ event, resolve }) => {
	event.locals.user = null;
	event.locals.token = null;

	const token = event.cookies.get(SESSION_COOKIE);
	if (token) {
		const response = await send(event.fetch, 'GET', '/auth/me', { token });
		if (response.ok) {
			event.locals.user = ((await response.json()) as Actor).user;
			event.locals.token = token;
		} else if (response.status === 401) {
			event.cookies.delete(SESSION_COOKIE, { path: '/' });
		} else {
			error(502, `The h2open server answered ${response.status}.`);
		}
	}

	if (!event.locals.user && event.route.id?.startsWith('/(app)')) redirect(303, '/login');

	return resolve(event);
};
