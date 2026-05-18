// Package main is a sample Go package for testing.
// It contains various constructs to verify the Go parser.
package main

import "fmt"

// ExportedConstant is a sample constant.
const ExportedConstant = "hello"

// unexportedConstant is not exported.
const unexportedConstant = "secret"

// ExportedVariable is a sample variable.
var ExportedVariable int = 42

// unexportedVariable is not exported.
var unexportedVariable = 0

// MyStruct is a sample struct.
type MyStruct struct {
	// Field is a public field.
	Field int
}

// MyMethod is an exported method on MyStruct.
func (s *MyStruct) MyMethod(param string) int {
	return len(param)
}

// unexportedMethod is not exported.
func (s *MyStruct) unexportedMethod() {}

// ExportedFunction is a sample function.
func ExportedFunction(a, b int) (int, error) {
	return a + b, nil
}

// unexportedFunction is not exported.
func unexportedFunction() {}

// MyInterface is a sample interface.
type MyInterface interface {
	// DoSomething is an interface method.
	DoSomething() string
}

// EmbeddedStruct uses embedding.
type EmbeddedStruct struct {
	MyStruct
	Other string
}

// MyAlias is a type alias.
type MyAlias = string

// MultiConst block.
const (
	C1 = iota
	C2
)

// MultiVar block.
var (
	V1 = 1
	V2 = 2
)
