<script lang="ts">
	import { enhance } from '$app/forms';
	import type { SubmitFunction } from '$app/forms';
	import EllipsisIcon from '@lucide/svelte/icons/ellipsis';
	import PlusIcon from '@lucide/svelte/icons/plus';
	import SearchIcon from '@lucide/svelte/icons/search';
	import { toast } from 'svelte-sonner';
	import type { ProductView } from '#lib/api.js';
	import * as AlertDialog from '#lib/components/ui/alert-dialog/index.js';
	import { Badge } from '#lib/components/ui/badge/index.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import { Checkbox } from '#lib/components/ui/checkbox/index.js';
	import * as Dialog from '#lib/components/ui/dialog/index.js';
	import * as DropdownMenu from '#lib/components/ui/dropdown-menu/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import { Label } from '#lib/components/ui/label/index.js';
	import * as Table from '#lib/components/ui/table/index.js';
	import { formatMoney, formatPercent } from '#lib/format.js';
	import ProductForm from './product-form.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const isAdmin = $derived(data.user.roles.includes('admin'));

	let search = $state('');
	let showInactive = $state(false);

	const shown = $derived.by(() => {
		const query = search.trim().toLowerCase();
		return data.products.filter(
			(product) =>
				(showInactive || product.active) &&
				(!query ||
					product.name.toLowerCase().includes(query) ||
					product.sku.toLowerCase().includes(query) ||
					product.barcode?.includes(query))
		);
	});

	function brandName(id: string | null): string {
		return data.brands.find((brand) => brand.id === id)?.name ?? '—';
	}

	function containerText(product: ProductView): string {
		if (!product.container) return '—';
		const { container_type_id, quantity } = product.container;
		const type = data.containerTypes.find((t) => t.id === container_type_id);
		return `${quantity} × ${type?.name ?? '?'}`;
	}

	// Add / edit dialog. `editing` is null when adding.
	let formOpen = $state(false);
	let editing = $state<ProductView | null>(null);

	function openForm(product: ProductView | null) {
		editing = product;
		formOpen = true;
	}

	// Deactivate / reactivate confirmation.
	let toggling = $state<ProductView | null>(null);
	let toggleOpen = $state(false);
	let togglePending = $state(false);

	function confirmToggle(product: ProductView) {
		toggling = product;
		toggleOpen = true;
	}

	type ToggleSuccess = { name: string; active: boolean };
	type ToggleFailure = { message: string };

	const submitToggle: SubmitFunction<ToggleSuccess, ToggleFailure> = () => {
		togglePending = true;
		return async ({ result, update }) => {
			togglePending = false;
			toggleOpen = false;
			if (result.type === 'failure') toast.error(result.data?.message ?? 'Not saved.');
			if (result.type === 'success' && result.data) {
				const { name, active } = result.data;
				toast.success(active ? `${name} is active again.` : `${name} deactivated.`);
			}
			await update();
		};
	};
</script>

<div class="flex flex-wrap items-center gap-3">
	<div class="relative w-full max-w-xs">
		<SearchIcon
			class="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
		/>
		<Input
			type="search"
			placeholder="Search name, SKU or barcode"
			aria-label="Search products"
			class="pl-8"
			bind:value={search}
		/>
	</div>
	<div class="flex items-center gap-2">
		<Checkbox id="show-inactive" bind:checked={showInactive} />
		<Label for="show-inactive">Show inactive</Label>
	</div>
	{#if isAdmin}
		<Button class="ml-auto" onclick={() => openForm(null)}>
			<PlusIcon />
			Add product
		</Button>
	{/if}
</div>

<div class="border">
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>SKU</Table.Head>
				<Table.Head>Name</Table.Head>
				<Table.Head>Brand</Table.Head>
				<Table.Head>Container</Table.Head>
				<Table.Head class="text-right">VAT</Table.Head>
				<Table.Head class="text-right">Price</Table.Head>
				<Table.Head>Status</Table.Head>
				{#if isAdmin}
					<Table.Head class="w-10"><span class="sr-only">Actions</span></Table.Head>
				{/if}
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#each shown as product (product.id)}
				<Table.Row class={product.active ? '' : 'text-muted-foreground'}>
					<Table.Cell class="font-mono">{product.sku}</Table.Cell>
					<Table.Cell class="font-medium">{product.name}</Table.Cell>
					<Table.Cell>{brandName(product.brand_id)}</Table.Cell>
					<Table.Cell>{containerText(product)}</Table.Cell>
					<Table.Cell class="text-right tabular-nums">
						{formatPercent(product.vat_rate)}
					</Table.Cell>
					<Table.Cell class="text-right tabular-nums">
						{product.price ? formatMoney(product.price) : 'No price'}
					</Table.Cell>
					<Table.Cell>
						{#if product.active}
							<Badge variant="secondary">Active</Badge>
						{:else}
							<Badge variant="outline">Inactive</Badge>
						{/if}
					</Table.Cell>
					{#if isAdmin}
						<Table.Cell>
							<DropdownMenu.Root>
								<DropdownMenu.Trigger>
									{#snippet child({ props })}
										<Button
											variant="ghost"
											size="icon-sm"
											aria-label="Actions for {product.name}"
											{...props}
										>
											<EllipsisIcon />
										</Button>
									{/snippet}
								</DropdownMenu.Trigger>
								<DropdownMenu.Content align="end">
									<DropdownMenu.Item onSelect={() => openForm(product)}>Edit</DropdownMenu.Item>
									<DropdownMenu.Item
										variant={product.active ? 'destructive' : 'default'}
										onSelect={() => confirmToggle(product)}
									>
										{product.active ? 'Deactivate' : 'Reactivate'}
									</DropdownMenu.Item>
								</DropdownMenu.Content>
							</DropdownMenu.Root>
						</Table.Cell>
					{/if}
				</Table.Row>
			{:else}
				<Table.Row>
					<Table.Cell colspan={isAdmin ? 8 : 7} class="h-24 text-center text-muted-foreground">
						{data.products.length === 0 ? 'No products yet.' : 'No products match.'}
					</Table.Cell>
				</Table.Row>
			{/each}
		</Table.Body>
	</Table.Root>
</div>

<Dialog.Root bind:open={formOpen}>
	<Dialog.Content class="sm:max-w-md">
		<ProductForm
			product={editing}
			brands={data.brands}
			containerTypes={data.containerTypes}
			onDone={() => (formOpen = false)}
		/>
	</Dialog.Content>
</Dialog.Root>

<AlertDialog.Root bind:open={toggleOpen}>
	<AlertDialog.Content>
		{#if toggling}
			<form method="POST" action="?/active" use:enhance={submitToggle}>
				<input type="hidden" name="id" value={toggling.id} />
				<input type="hidden" name="active" value={String(!toggling.active)} />
				<AlertDialog.Header>
					<AlertDialog.Title>
						{toggling.active ? 'Deactivate' : 'Reactivate'}
						{toggling.name}?
					</AlertDialog.Title>
					<AlertDialog.Description>
						{#if toggling.active}
							It will no longer be offered for sale. Products are never deleted, because past
							orders, stock and container balances refer to them. You can reactivate it later.
						{:else}
							It will be offered for sale again.
						{/if}
					</AlertDialog.Description>
				</AlertDialog.Header>
				<AlertDialog.Footer class="mt-4">
					<AlertDialog.Cancel type="button">Cancel</AlertDialog.Cancel>
					<AlertDialog.Action
						type="submit"
						variant={toggling.active ? 'destructive' : 'default'}
						disabled={togglePending}
					>
						{toggling.active ? 'Deactivate' : 'Reactivate'}
					</AlertDialog.Action>
				</AlertDialog.Footer>
			</form>
		{/if}
	</AlertDialog.Content>
</AlertDialog.Root>
