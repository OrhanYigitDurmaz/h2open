<!-- Add a product (product is null) or edit one. Mounted fresh each time the dialog opens. -->
<script lang="ts">
	import { enhance } from '$app/forms';
	import type { SubmitFunction } from '$app/forms';
	import { toast } from 'svelte-sonner';
	import type { BrandView, ContainerTypeView, ProductView } from '#lib/api.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Dialog from '#lib/components/ui/dialog/index.js';
	import * as Field from '#lib/components/ui/field/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import * as Select from '#lib/components/ui/select/index.js';
	import { CURRENCY } from '#lib/format.js';

	interface Props {
		product: ProductView | null;
		brands: BrandView[];
		containerTypes: ContainerTypeView[];
		/** Called after a successful save. */
		onDone: () => void;
	}

	let { product, brands, containerTypes, onDone }: Props = $props();

	type Failure = {
		message: string;
		fields: Record<string, string>;
	};
	type Success = {
		name: string;
		warning?: string;
	};

	let failure = $state<Failure | null>(null);
	let pending = $state(false);
	let brandId = $state('');
	let containerTypeId = $state('');

	const activeBrands = $derived(brands.filter((brand) => brand.active));
	// A product's containers must be its own brand's.
	const brandContainers = $derived(
		containerTypes.filter((type) => type.active && type.brand_id === brandId)
	);
	const brandLabel = $derived(brands.find((brand) => brand.id === brandId)?.name ?? 'No brand');
	const containerLabel = $derived(
		containerTypes.find((type) => type.id === containerTypeId)?.name ?? 'No container'
	);

	function error(field: string): string | undefined {
		return failure?.fields[field];
	}

	const submit: SubmitFunction<Success, Failure> = () => {
		pending = true;
		return async ({ result, update }) => {
			pending = false;
			if (result.type === 'failure') {
				failure = result.data ?? null;
				return;
			}
			if (result.type === 'success' && result.data) {
				const { name, warning } = result.data;
				if (warning) toast.warning(`${name} was added. ${warning}`);
				else toast.success(product ? `${name} saved.` : `${name} added.`);
				onDone();
			}
			await update();
		};
	};

	function nameOf<T extends { id: string; name: string }>(items: T[], id: string | null) {
		return items.find((item) => item.id === id)?.name;
	}
</script>

<form method="POST" action={product ? '?/update' : '?/create'} use:enhance={submit}>
	<Dialog.Header>
		<Dialog.Title>{product ? 'Edit product' : 'Add product'}</Dialog.Title>
		<Dialog.Description>
			{product
				? 'The SKU, brand and container are fixed once a product exists.'
				: 'The SKU, brand and container cannot be changed later.'}
		</Dialog.Description>
	</Dialog.Header>

	<Field.Group class="py-4">
		{#if product}
			<input type="hidden" name="id" value={product.id} />
			<dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
				<dt class="text-muted-foreground">SKU</dt>
				<dd class="font-mono">{product.sku}</dd>
				<dt class="text-muted-foreground">Brand</dt>
				<dd>{nameOf(brands, product.brand_id) ?? '—'}</dd>
				<dt class="text-muted-foreground">Container</dt>
				<dd>
					{#if product.container}
						{product.container.quantity} × {nameOf(
							containerTypes,
							product.container.container_type_id
						)}
					{:else}
						—
					{/if}
				</dd>
			</dl>
		{:else}
			<Field.Field data-invalid={!!error('sku')}>
				<Field.Label for="sku">SKU</Field.Label>
				<Input id="sku" name="sku" required maxlength={50} aria-invalid={!!error('sku')} />
				<Field.Error>{error('sku')}</Field.Error>
			</Field.Field>
		{/if}

		<Field.Field data-invalid={!!error('name')}>
			<Field.Label for="name">Name</Field.Label>
			<Input
				id="name"
				name="name"
				required
				maxlength={200}
				value={product?.name ?? ''}
				aria-invalid={!!error('name')}
			/>
			<Field.Error>{error('name')}</Field.Error>
		</Field.Field>

		<Field.Field data-invalid={!!error('barcode')}>
			<Field.Label for="barcode">Barcode</Field.Label>
			<Input
				id="barcode"
				name="barcode"
				maxlength={50}
				inputmode="numeric"
				value={product?.barcode ?? ''}
				aria-invalid={!!error('barcode')}
			/>
			<Field.Error>{error('barcode')}</Field.Error>
		</Field.Field>

		<div class="grid grid-cols-2 gap-4">
			<Field.Field data-invalid={!!error('vat_rate')}>
				<Field.Label for="vat_rate">VAT rate (%)</Field.Label>
				<Input
					id="vat_rate"
					name="vat_rate"
					required
					inputmode="decimal"
					placeholder="20"
					value={product ? Number(product.vat_rate) : ''}
					aria-invalid={!!error('vat_rate')}
				/>
				<Field.Error>{error('vat_rate')}</Field.Error>
			</Field.Field>

			<Field.Field data-invalid={!!error('price.amount')}>
				<Field.Label for="price">Price ({product?.price?.currency ?? CURRENCY})</Field.Label>
				<Input
					id="price"
					name="price"
					inputmode="decimal"
					placeholder="0,00"
					value={product?.price ? Number(product.price.amount) : ''}
					aria-invalid={!!error('price.amount')}
				/>
				<Field.Error>{error('price.amount')}</Field.Error>
			</Field.Field>
		</div>

		{#if !product}
			<Field.Field data-invalid={!!error('brand_id')}>
				<Field.Label for="brand_id">Brand</Field.Label>
				<Select.Root
					type="single"
					name="brand_id"
					bind:value={brandId}
					onValueChange={() => (containerTypeId = '')}
				>
					<Select.Trigger id="brand_id" class="w-full">{brandLabel}</Select.Trigger>
					<Select.Content>
						<Select.Item value="" label="No brand">No brand</Select.Item>
						{#each activeBrands as brand (brand.id)}
							<Select.Item value={brand.id} label={brand.name}>{brand.name}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
				<Field.Description>Leave empty for generic products.</Field.Description>
				<Field.Error>{error('brand_id')}</Field.Error>
			</Field.Field>

			{#if brandContainers.length > 0}
				<div class="grid grid-cols-[1fr_6rem] gap-4">
					<Field.Field data-invalid={!!error('container.container_type_id')}>
						<Field.Label for="container_type_id">Returnable container</Field.Label>
						<Select.Root type="single" name="container_type_id" bind:value={containerTypeId}>
							<Select.Trigger id="container_type_id" class="w-full">
								{containerLabel}
							</Select.Trigger>
							<Select.Content>
								<Select.Item value="" label="No container">No container</Select.Item>
								{#each brandContainers as type (type.id)}
									<Select.Item value={type.id} label={type.name}>{type.name}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
						<Field.Error>{error('container.container_type_id')}</Field.Error>
					</Field.Field>

					{#if containerTypeId}
						<Field.Field data-invalid={!!error('container.quantity')}>
							<Field.Label for="container_quantity">Quantity</Field.Label>
							<Input
								id="container_quantity"
								name="container_quantity"
								type="number"
								min={1}
								step={1}
								value={1}
								required
								aria-invalid={!!error('container.quantity')}
							/>
							<Field.Error>{error('container.quantity')}</Field.Error>
						</Field.Field>
					{/if}
				</div>
			{/if}
		{/if}

		{#if failure && Object.keys(failure.fields).length === 0}
			<p class="text-xs text-destructive" role="alert">{failure.message}</p>
		{/if}
	</Field.Group>

	<Dialog.Footer>
		<Dialog.Close>
			{#snippet child({ props })}
				<Button variant="outline" {...props}>Cancel</Button>
			{/snippet}
		</Dialog.Close>
		<Button type="submit" disabled={pending}>
			{pending ? 'Saving…' : product ? 'Save' : 'Add product'}
		</Button>
	</Dialog.Footer>
</form>
