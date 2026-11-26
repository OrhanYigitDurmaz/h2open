import { error, fail, redirect } from '@sveltejs/kit';
import type { LoginResult } from '#lib/api.js';
import { send, SESSION_COOKIE } from '#lib/server/backend.js';
import { text } from '#lib/server/form.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = ({ locals }) => {
	if (locals.user) redirect(303, '/');
};

export const actions = {
	login: async ({ request, fetch, cookies, url }) => {
		const data = await request.formData();
		const username = text(data, 'username');
		const password = data.get('password');
		if (!username || typeof password !== 'string' || !password) {
			return fail(400, { username, message: 'Enter your username and password.' });
		}

		const response = await send(fetch, 'POST', '/auth/login', {
			body: {
				username,
				password,
				platform: 'web',
				// Shown in the user's list of logins.
				client_name: request.headers.get('user-agent')?.slice(0, 100) ?? null
			}
		});
		// The backend never says which part was wrong, and 422 means the
		// password is longer than any valid one.
		if (response.status === 401 || response.status === 422) {
			return fail(401, {
				username,
				message:
					'Wrong username or password. After several failed tries the account is locked for a while.'
			});
		}
		if (!response.ok) error(502, `The h2open server answered ${response.status}.`);

		const result = (await response.json()) as LoginResult;
		cookies.set(SESSION_COOKIE, result.token, {
			path: '/',
			httpOnly: true,
			sameSite: 'strict',
			// The shop may serve this over plain HTTP on the LAN.
			secure: url.protocol === 'https:',
			expires: new Date(result.expires_at)
		});
		redirect(303, '/');
	},

	logout: async ({ fetch, cookies, locals }) => {
		if (locals.token) {
			// Ends the login on the backend too; a failure here still logs out locally.
			await send(fetch, 'POST', '/auth/logout', { token: locals.token }).catch(() => undefined);
		}
		cookies.delete(SESSION_COOKIE, { path: '/' });
		redirect(303, '/login');
	}
} satisfies Actions;
