<?php
/**
 * File-level PHPDoc.
 */

namespace Sample;

/**
 * A public class with PHPDoc.
 */
class SampleClass extends BaseClass implements SampleInterface {
    /**
     * A public constant.
     */
    public const PUBLIC_CONST = 'value';

    /**
     * A public property.
     */
    public string $publicProp = 'default';

    /**
     * A protected property.
     */
    protected $protectedProp;

    /**
     * A private property.
     */
    private $privateProp;

    /**
     * A public method.
     * @param string $input
     * @return string
     */
    public function publicMethod(string $input): string {
        return $input;
    }

    /**
     * An unscoped method (defaults to public).
     */
    function unscopedMethod() {}

    /**
     * A protected method.
     */
    protected function protectedMethod() {}

    /**
     * A private method.
     */
    private function privateMethod() {}
}

/**
 * A global function.
 */
function globalFunction(int $x, $y = 10): void {}

/**
 * An interface.
 */
interface SampleInterface {
    public function foo();
}

/**
 * A trait.
 */
trait SampleTrait {
    public function traitMethod() {}
}

/**
 * An enum.
 */
enum SampleEnum: string {
    case A = 'a';
    case B = 'b';
}
