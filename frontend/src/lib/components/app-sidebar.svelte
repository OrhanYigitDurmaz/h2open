<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import DropletIcon from '@lucide/svelte/icons/droplet';
	import LogOutIcon from '@lucide/svelte/icons/log-out';
	import * as Sidebar from '#lib/components/ui/sidebar/index.js';
	import type { UserView } from '#lib/api.js';
	import { sections } from '#lib/navigation.js';

	let { user }: { user: UserView } = $props();
</script>

<Sidebar.Root collapsible="icon">
	<Sidebar.Header>
		<Sidebar.Menu>
			<Sidebar.MenuItem>
				<Sidebar.MenuButton size="lg" tooltipContent="h2open">
					{#snippet child({ props })}
						<a href={resolve('/(app)')} {...props}>
							<DropletIcon class="text-primary" />
							<span class="text-sm font-semibold">h2open</span>
						</a>
					{/snippet}
				</Sidebar.MenuButton>
			</Sidebar.MenuItem>
		</Sidebar.Menu>
	</Sidebar.Header>

	<Sidebar.Content>
		<Sidebar.Group>
			<Sidebar.GroupLabel>Catalog</Sidebar.GroupLabel>
			<Sidebar.GroupContent>
				<Sidebar.Menu>
					{#each sections as section (section.route)}
						<Sidebar.MenuItem>
							<Sidebar.MenuButton
								isActive={page.url.pathname.startsWith(section.path)}
								tooltipContent={section.title}
							>
								{#snippet child({ props })}
									<a href={resolve(section.route)} {...props}>
										<section.icon />
										<span>{section.title}</span>
									</a>
								{/snippet}
							</Sidebar.MenuButton>
						</Sidebar.MenuItem>
					{/each}
				</Sidebar.Menu>
			</Sidebar.GroupContent>
		</Sidebar.Group>
	</Sidebar.Content>

	<Sidebar.Footer>
		<Sidebar.Menu>
			<Sidebar.MenuItem>
				<div class="truncate px-2 py-1 text-xs group-data-[collapsible=icon]:hidden">
					<div class="truncate font-medium">{user.name}</div>
					<div class="truncate text-muted-foreground">{user.roles.join(', ')}</div>
				</div>
			</Sidebar.MenuItem>
			<Sidebar.MenuItem>
				<form method="POST" action="{resolve('/login')}?/logout">
					<Sidebar.MenuButton tooltipContent="Log out">
						{#snippet child({ props })}
							<button type="submit" {...props}>
								<LogOutIcon />
								<span>Log out</span>
							</button>
						{/snippet}
					</Sidebar.MenuButton>
				</form>
			</Sidebar.MenuItem>
		</Sidebar.Menu>
	</Sidebar.Footer>

	<Sidebar.Rail />
</Sidebar.Root>
