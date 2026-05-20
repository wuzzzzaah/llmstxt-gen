/**
 * Module-level KDoc.
 */
package com.example

/**
 * A public class with KDoc.
 */
class SampleClass<T>(val publicProp: String, private val privateProp: Int) {
    /**
     * A public method.
     */
    fun publicMethod(input: String = "default"): String {
        return input
    }

    protected fun protectedMethod() {}

    private fun privateMethod() {}

    internal fun internalMethod() {}

    companion object {
        /**
         * Method in companion object.
         */
        fun companionMethod() {}

        val companionProp = 42
    }
}

/**
 * Data class.
 */
data class SampleData(val x: Int, val y: Int)

/**
 * Extension function.
 */
fun String.shout(): String = this.uppercase()

/**
 * Top-level property.
 */
val topLevelVal = "Hello"

private val privateTopLevelVal = "Secret"

/**
 * Sealed class and subclasses.
 */
sealed class Expr
data class Const(val number: Double) : Expr()
data class Sum(val left: Expr, val right: Expr) : Expr()

/**
 * Interface.
 */
interface SampleInterface {
    fun foo()
}

/**
 * Enum.
 */
enum class Color { RED, GREEN, BLUE }

/**
 * Singleton object.
 */
object Singleton {
    fun greet() = "Hello"
}

@Deprecated("use bar")
fun annotatedFun() {}
