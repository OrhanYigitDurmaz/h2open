import { fail, type RequestEvent } from '@sveltejs/kit';
import type { BrandView, ContainerTypeView, ProductView } from '#lib/api.js';
import { CURRENCY } from '#lib/format.js';
import { backend, BackendError, get } from '#lib/server/backend.js';
import { decimal, optional, text } from '#lib/server/form.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async (event) => {
	const [products, brands, containerTypes] = await Promise.all([
		get<ProductView[]>(event, '/catalog/products'),
		get<BrandView[]>(event, '/catalog/brands'),
		get<ContainerTypeView[]>(event, '/catalog/container-types')
	]);
	return { products, brands, containerTypes };
};

type Form = 'create' | 'update' | 'active';

/** Turn a refusal into form errors; anything else (a redirect, say) goes on. */
function refused(form: Form, e: unknown) {
	if (e instanceof BackendError) {
		return fail(e.status, { form, message: e.message, fields: e.fields });
	}
	throw e;
}

function productPath(id: string): string {
	return `/catalog/products/${encodeURIComponent(id)}`;
}

/** A price typed as "12.50": checked before the product is saved, as it is a second call. */
function badPrice(form: Form, price: string) {
	if (!price || /^\d+(\.\d+)?$/.test(price)) return null;
	return fail(400, {
		form,
		message: 'Some fields need fixing.',
		fields: { 'price.amount': 'Enter a price such as 12,50.' }
	});
}

async function setPrice(event: RequestEvent, productId: string, amount: string): Promise<void> {
	await backend(event, 'POST', `${productPath(productId)}/prices`, {
		price: { amount, currency: CURRENCY }
	});
}

export const actions = {
	create: async (event) => {
		const data = await event.request.formData();
		const containerTypeId = optional(data, 'container_type_id');
		const price = decimal(data, 'price');
		const priceError = badPrice('create', price);
		if (priceError) return priceError;

		let product: ProductView;
		try {
			product = await backend<ProductView>(event, 'POST', '/catalog/products', {
				sku: text(data, 'sku'),
				name: text(data, 'name'),
				barcode: optional(data, 'barcode'),
				brand_id: optional(data, 'brand_id'),
				vat_rate: decimal(data, 'vat_rate'),
				container: containerTypeId && {
					container_type_id: containerTypeId,
					quantity: Number(text(data, 'container_quantity'))
				}
			});
		} catch (e) {
			return refused('create', e);
		}

		// A second call: a product is created without a price.
		if (price) {
			try {
				await setPrice(event, product.id, price);
			} catch (e) {
				if (!(e instanceof BackendError)) throw e;
				const reason = e.fields['price.amount'] ?? e.message;
				return { form: 'create', name: product.name, warning: `Price not saved: ${reason}` };
			}
		}
		return { form: 'create', name: product.name };
	},

	update: async (event) => {
		const data = await event.request.formData();
		const id = text(data, 'id');
		const price = decimal(data, 'price');
		const priceError = badPrice('update', price);
		if (priceError) return priceError;
		try {
			const product = await backend<ProductView>(event, 'PATCH', productPath(id), {
				name: text(data, 'name'),
				barcode: optional(data, 'barcode'),
				vat_rate: decimal(data, 'vat_rate')
			});
			// Prices are a history: only add an entry when it changed.
			if (price && Number(price) !== Number(product.price?.amount)) {
				await setPrice(event, id, price);
			}
			return { form: 'update', name: product.name };
		} catch (e) {
			return refused('update', e);
		}
	},

	active: async (event) => {
		const data = await event.request.formData();
		try {
			const product = await backend<ProductView>(event, 'PATCH', productPath(text(data, 'id')), {
				active: text(data, 'active') === 'true'
			});
			return { form: 'active', name: product.name, active: product.active };
		} catch (e) {
			return refused('active', e);
		}
	}
} satisfies Actions;
