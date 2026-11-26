// Shapes of the h2open API responses this app uses (see docs/openapi.json).

export type Role = 'admin' | 'staff' | 'driver';

export interface Money {
	/** A decimal string, such as "12.50". */
	amount: string;
	/** ISO 4217, such as "TRY". */
	currency: string;
}

export interface UserView {
	id: string;
	username: string;
	name: string;
	roles: Role[];
	active: boolean;
	on_shift: boolean;
}

export interface Actor {
	user: UserView;
	session_id: string;
}

export interface LoginResult {
	token: string;
	expires_at: string;
	user: UserView;
}

export interface BrandView {
	id: string;
	name: string;
	active: boolean;
}

export interface ContainerTypeView {
	id: string;
	brand_id: string;
	name: string;
	active: boolean;
	deposit: Money | null;
}

/** How many of a brand's returnable containers one unit of a product uses. */
export interface ContainerLink {
	container_type_id: string;
	quantity: number;
}

export interface ProductView {
	id: string;
	sku: string;
	name: string;
	barcode: string | null;
	brand_id: string | null;
	/** A decimal string, such as "20.00". */
	vat_rate: string;
	container: ContainerLink | null;
	active: boolean;
	price: Money | null;
}
