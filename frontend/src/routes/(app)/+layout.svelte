<script lang="ts">
	import { page } from '$app/state';
	import AppSidebar from '#lib/components/app-sidebar.svelte';
	import { sections } from '#lib/navigation.js';
	import { Separator } from '#lib/components/ui/separator/index.js';
	import * as Sidebar from '#lib/components/ui/sidebar/index.js';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	const title = $derived(
		sections.find((section) => page.url.pathname.startsWith(section.path))?.title ?? 'h2open'
	);
</script>

<svelte:head>
	<title>{title} · h2open</title>
</svelte:head>

<Sidebar.Provider>
	<AppSidebar user={data.user} />
	<Sidebar.Inset>
		<header class="flex h-12 shrink-0 items-center gap-2 border-b px-4">
			<Sidebar.Trigger class="-ml-1" />
			<Separator orientation="vertical" class="mr-2 data-[orientation=vertical]:h-4" />
			<h1 class="text-sm font-medium">{title}</h1>
		</header>
		<main class="flex flex-1 flex-col gap-4 p-4">
			{@render children()}
		</main>
	</Sidebar.Inset>
</Sidebar.Provider>
