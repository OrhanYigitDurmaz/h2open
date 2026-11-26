import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

// Products is the only section so far.
export const load: PageServerLoad = () => {
	redirect(307, '/products');
};
