import PackageIcon from '@lucide/svelte/icons/package';

/** The sections of the app, in sidebar order. */
export const sections = [
	{ title: 'Products', route: '/(app)/products', path: '/products', icon: PackageIcon }
] as const;
