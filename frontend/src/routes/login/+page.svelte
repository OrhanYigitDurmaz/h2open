<script lang="ts">
	import { enhance } from '$app/forms';
	import DropletIcon from '@lucide/svelte/icons/droplet';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Card from '#lib/components/ui/card/index.js';
	import * as Field from '#lib/components/ui/field/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import type { PageProps } from './$types';

	let { form }: PageProps = $props();
	let pending = $state(false);
</script>

<svelte:head>
	<title>Log in · h2open</title>
</svelte:head>

<main class="grid min-h-svh place-items-center bg-muted/40 p-4">
	<Card.Root class="w-full max-w-sm">
		<Card.Header>
			<div class="mb-2 flex items-center gap-2 text-sm font-semibold">
				<DropletIcon class="size-5 text-primary" />
				h2open
			</div>
			<Card.Title>Log in</Card.Title>
			<Card.Description>Use the account your admin gave you.</Card.Description>
		</Card.Header>
		<Card.Content>
			<form
				method="POST"
				action="?/login"
				use:enhance={() => {
					pending = true;
					return async ({ update }) => {
						await update({ reset: false });
						pending = false;
					};
				}}
			>
				<Field.Group>
					<Field.Field>
						<Field.Label for="username">Username</Field.Label>
						<Input
							id="username"
							name="username"
							autocomplete="username"
							autocapitalize="none"
							spellcheck={false}
							required
							value={form?.username ?? ''}
						/>
					</Field.Field>
					<Field.Field>
						<Field.Label for="password">Password</Field.Label>
						<Input
							id="password"
							name="password"
							type="password"
							autocomplete="current-password"
							required
						/>
					</Field.Field>
					{#if form?.message}
						<p class="text-xs text-destructive" role="alert">{form.message}</p>
					{/if}
					<Button type="submit" disabled={pending}>
						{pending ? 'Logging in…' : 'Log in'}
					</Button>
				</Field.Group>
			</form>
		</Card.Content>
	</Card.Root>
</main>
