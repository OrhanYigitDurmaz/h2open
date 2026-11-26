import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	BACKEND_URL: {
		description: 'Where this server reaches the h2open API. The browser never calls it directly.',
		schema: (value) => {
			const url = new URL(value || 'http://127.0.0.1:8000');
			return url.href.replace(/\/$/, '');
		}
	}
});
