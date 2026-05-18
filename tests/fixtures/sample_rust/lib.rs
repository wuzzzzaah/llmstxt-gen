//! This is a module doc comment.
//! It covers multiple lines.

/// A public struct.
pub struct MyStruct {
    /// A public field.
    pub field: i32,
    /// A private field.
    private_field: String,
}

impl MyStruct {
    /// A public method on a struct.
    pub fn new(field: i32) -> Self {
        Self { field, private_field: String::new() }
    }

    /// A private method.
    fn private_method(&self) {}
}

/// A public enum.
pub enum MyEnum {
    /// Variant A.
    VariantA,
    /// Variant B with data.
    VariantB(i32),
}

/// A public trait.
pub trait MyTrait {
    /// A trait method signature.
    fn trait_method(&self) -> bool;
}

impl MyTrait for MyStruct {
    fn trait_method(&self) -> bool {
        true
    }
}

/// A public type alias.
pub type MyAlias = Vec<MyStruct>;

/// A public constant.
pub const MY_CONST: u32 = 42;

/// A public static.
pub static MY_STATIC: &str = "hello";

/// A public function.
pub fn public_fn<T>(arg: T) -> T where T: Clone {
    arg.clone()
}

/// pub(crate) visibility.
pub(crate) fn crate_visible() {}

/// pub(super) visibility.
pub(super) fn super_visible() {}

fn private_fn() {}
